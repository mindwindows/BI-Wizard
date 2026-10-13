"""가짜 Superset(`httpx.MockTransport` 기반): 프로브 문서(`docs/research/fu1e-probes.md`)의 실제
요청·응답
모양을 따른다.

- 로그인(JWT 접근/갱신 토큰), 세션 쿠키 + CSRF 토큰(POST/PUT 필수, 없으면 400 `CSRF`), 데이터셋
  조회·
  등록·새로고침·전체 열 `PUT`(`columns`는 병합이 아니라 **교체**: 빠진 열은 지워진다), 입장권
  발급(훅 거부 5가지와
  모르는 uuid는 400), 접근 토큰 만료(401 `Token has expired`), 형식이 깨진 토큰(422).
- `up=False`이면 모든 요청이 연결 거부(`httpx.ConnectError`)다(시도는 `calls`에 남는다).
  `slow=True`이면 시간 초과.
- `calls`에 (메서드, 경로, 본문) 기록이 쌓인다. 비밀번호·토큰은 기록하지 않는다.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, unquote

import httpx

ROOT = "/bi-wizard/superset"
DB_NAME = "BI-Wizard (read-only)"
_FILTER = re.compile(r"\(col:(\w+),opr:eq,value:'((?:[^'!]|![!'])*)'\)")
_VIEW = re.compile(r"SELECT \* FROM bi_data\.dv_([0-9]+)")


@dataclass
class Call:
    method: str
    path: str  # 접두(ROOT) 뗀 경로
    body: Any = None
    params: dict[str, str] = field(default_factory=dict)
    account: str | None = None


class FakeSuperset:
    def __init__(self) -> None:
        self.up = True
        self.slow = False
        self.health_ok = True
        self.accounts: dict[str, str] = {}
        self.roles: dict[str, str] = {}  # 계정 -> "service" | "issuer"
        self.database_id = 1
        self.database_name = DB_NAME
        self.dataset_database_name: str | None = (
            None  # 등록된 데이터셋의 DB 이름 재정의(DB_MISMATCH 시험)
        )
        self.embedded_uuids: set[str] = set()
        self.datasets: dict[int, dict[str, Any]] = {}
        self.views: dict[int, list[str]] = {}  # 데이터셋 번호 -> 뷰 열 이름(없으면 team,row_id)
        self.missing_views: set[int] = set()
        self.foreign_datasets: set[int] = set()  # 서비스 계정이 소유하지 않은 데이터셋(403)
        self.calls: list[Call] = []
        self.tokens_issued: list[str] = []
        self.expired: set[str] = set()
        self._next_dataset = 1
        self._next_column = 1
        self._counter = 0
        self._access: dict[str, str] = {}  # 접근 토큰 -> 계정
        self._refresh: dict[str, str] = {}
        self._csrf: dict[str, str] = {}  # CSRF 토큰 -> 세션 쿠키
        self.logins = 0
        self.refreshes = 0
        self.inject: list[tuple[Callable[[Call], bool], Callable[[Call], httpx.Response]]] = []
        self.transport = httpx.MockTransport(self._handle)

    # --- 시험 도구 ---

    def add_account(self, username: str, password: str, role: str) -> None:
        self.accounts[username] = password
        self.roles[username] = role

    def count(self, method: str, prefix: str) -> int:
        return sum(1 for c in self.calls if c.method == method and c.path.startswith(prefix))

    def expire_all_access_tokens(self) -> None:
        self.expired |= set(self._access)

    def respond_once(
        self, match: Callable[[Call], bool], response: Callable[[Call], httpx.Response]
    ) -> None:
        self.inject.append((match, response))

    def view_columns(self, dataset_id: int) -> list[str]:
        return self.views.get(dataset_id, ["team", "row_id"])

    # --- 응답 ---

    @staticmethod
    def _json(data: Any, status: int = 200, headers: dict[str, str] | None = None):
        return httpx.Response(status, json=data, headers=headers)

    def _new(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        assert path.startswith(ROOT), path
        rel = path[len(ROOT) :]
        body = json.loads(request.content) if request.content else None
        params = dict(request.url.params)
        auth = request.headers.get("authorization", "")
        account = self._access.get(auth.removeprefix("Bearer ")) if auth else None
        call = Call(request.method, rel, body, params, account)
        if rel != "/api/v1/security/login" or body is None:
            logged = call
        else:
            logged = Call(request.method, rel, {"username": body.get("username")}, params, None)
        self.calls.append(logged)
        if not self.up:
            raise httpx.ConnectError("connection refused", request=request)
        if self.slow:
            raise httpx.ReadTimeout("timed out", request=request)
        for index, (match, respond) in enumerate(self.inject):
            if match(call):
                del self.inject[index]
                return respond(call)
        if rel == "/health":
            return httpx.Response(
                200 if self.health_ok else 503, text="OK" if self.health_ok else "no"
            )
        if rel == "/api/v1/security/login":
            return self._login(body)
        if rel == "/api/v1/security/refresh":
            return self._refresh_token(auth)
        token = auth.removeprefix("Bearer ")
        if not auth:
            return self._json({"msg": "Missing Authorization Header"}, 401)
        if token in self.expired:
            return self._json({"msg": "Token has expired"}, 401)
        if token not in self._access:
            return self._json({"msg": "Not enough segments"}, 422)
        role = self.roles[self._access[token]]
        if request.method in ("POST", "PUT", "DELETE") and rel != "/api/v1/security/login":
            bad = self._csrf_problem(request)
            if bad is not None:
                return bad
        if rel == "/api/v1/security/csrf_token/":
            csrf = self._new("csrf")
            session = self._new("sess")
            self._csrf[csrf] = session
            return self._json(
                {"result": csrf},
                headers={"set-cookie": f"session={session}; Path={ROOT}; HttpOnly"},
            )
        if rel == "/api/v1/security/guest_token/":
            return self._guest_token(role, body)
        if role != "service":
            return self._json({"message": "Forbidden"}, 403)
        return self._dataset_api(request.method, rel, params, body)

    def _login(self, body: dict[str, Any] | None) -> httpx.Response:
        assert body is not None
        user = body.get("username")
        if self.accounts.get(user) != body.get("password"):
            return self._json({"message": "Not authorized"}, 401)
        self.logins += 1
        access, refresh = self._new("AT"), self._new("RT")
        self._access[access] = user
        self._refresh[refresh] = user
        return self._json({"access_token": access, "refresh_token": refresh})

    def _refresh_token(self, auth: str) -> httpx.Response:
        user = self._refresh.get(auth.removeprefix("Bearer "))
        if user is None:
            return self._json({"msg": "Not authorized"}, 401)
        self.refreshes += 1
        access = self._new("AT")
        self._access[access] = user
        return self._json({"access_token": access})

    def _csrf_problem(self, request: httpx.Request) -> httpx.Response | None:
        token = request.headers.get("x-csrftoken")
        cookie = request.headers.get("cookie", "")
        if not token:
            return self._csrf_400("The CSRF token is missing.")
        session = self._csrf.get(token)
        if session is None or f"session={session}" not in cookie:
            return self._csrf_400("The CSRF token is invalid.")
        return None

    def _csrf_400(self, text: str) -> httpx.Response:
        return self._json(
            {
                "errors": [
                    {
                        "message": f"400 Bad Request: {text}",
                        "error_type": "GENERIC_BACKEND_ERROR",
                        "level": "error",
                        "extra": {},
                    }
                ]
            },
            400,
        )

    def _guest_token(self, role: str, body: dict[str, Any] | None) -> httpx.Response:
        if role != "issuer":
            return self._json({"message": "Forbidden"}, 403)
        reject = self._json({"message": ["Guest token validation failed"]}, 400)
        if not isinstance(body, dict) or not isinstance(body.get("rls"), list):
            return self._json({"message": {"rls": ["Missing data for required field."]}}, 400)
        resources = body.get("resources")
        user = body.get("user")
        if body["rls"] or not isinstance(resources, list) or len(resources) != 1:
            return reject
        resource = resources[0]
        if resource.get("type") != "dashboard":
            return self._json(
                {"message": {"resources": {"0": {"type": ["Must be one of: dashboard."]}}}}, 400
            )
        # 실제 6.1.0(프로브 P-3): 훅의 형식 검사는 `str(uuid.UUID(v)) == v.lower()`라 **대문자도 통과**하고
        # Superset 기본 검사의 임베드 조회도 대소문자를 가리지 않는다(토큰의 resource id는 보낸 그대로).
        resource_id = resource.get("id")
        try:
            well_formed = isinstance(resource_id, str) and (
                str(uuid.UUID(resource_id)) == resource_id.lower()
            )
        except ValueError:
            well_formed = False
        if not well_formed:
            return reject
        if resource_id.lower() not in {u.lower() for u in self.embedded_uuids}:
            return self._json({"message": "EmbeddedDashboard not found."}, 400)
        if not isinstance(user, dict) or not user.get("username"):
            return reject
        token = "eyJ" + self._new("GUESTTOKEN").replace("-", "") + "." + uuid.uuid4().hex
        self.tokens_issued.append(token)
        return self._json({"token": token})

    # --- 데이터셋 API ---

    def _dataset_api(
        self, method: str, rel: str, params: dict[str, str], body: Any
    ) -> httpx.Response:
        if rel == "/api/v1/dataset/related/database" and method == "GET":
            return self._json(
                {
                    "count": 1,
                    "result": [
                        {"extra": {}, "text": self.database_name, "value": self.database_id}
                    ],
                }
            )
        if rel == "/api/v1/dataset/" and method == "GET":
            return self._search(params.get("q", ""))
        if rel == "/api/v1/dataset/" and method == "POST":
            return self._create(body)
        match = re.fullmatch(r"/api/v1/dataset/([0-9]+)(/refresh)?", rel)
        if match is None:
            return self._json({"message": "Not Found"}, 404)
        dataset_id = int(match.group(1))
        dataset = self.datasets.get(dataset_id)
        if dataset is None:
            return self._json({"message": "Not found"}, 404)
        if method != "GET" and dataset_id in self.foreign_datasets:
            return self._json({"message": "Forbidden"}, 403)
        if match.group(2):
            return self._refresh_dataset(dataset_id, dataset)
        if method == "GET":
            return self._json({"id": dataset_id, "result": self._detail(dataset)})
        if method == "PUT":
            return self._put(dataset_id, dataset, body)
        return self._json({"message": "Method Not Allowed"}, 405)

    def _detail(self, dataset: dict[str, Any]) -> dict[str, Any]:
        return {
            "table_name": dataset["table_name"],
            "sql": dataset["sql"],
            "schema": "bi_data",
            "columns": [dict(c) for c in dataset["columns"]],
            "database": {
                "database_name": self.dataset_database_name or self.database_name,
                "id": self.database_id,
            },
            "metrics": [{"id": 1, "metric_name": "count"}],
        }

    def _search(self, q: str) -> httpx.Response:
        filters = {col: re.sub(r"!(.)", r"\1", raw) for col, raw in _FILTER.findall(q)}
        hits = [
            {"id": i, "schema": "bi_data", "sql": d["sql"], "table_name": d["table_name"]}
            for i, d in sorted(self.datasets.items())
            if all(
                {"sql": d["sql"], "table_name": d["table_name"], "schema": "bi_data"}.get(c) == v
                for c, v in filters.items()
            )
        ]
        return self._json({"count": len(hits), "ids": [h["id"] for h in hits], "result": hits})

    def _create(self, body: dict[str, Any]) -> httpx.Response:
        name = body["table_name"]
        if any(d["table_name"] == name for d in self.datasets.values()):
            return self._json(
                {"message": {"table": [f"Dataset bi_wizard.bi_data.{quote(name)} already exists"]}},
                422,
            )
        match = _VIEW.fullmatch(body["sql"])
        view_id = int(match.group(1)) if match else None
        if view_id is None or view_id in self.missing_views:
            return self._json({"message": {"sql": ["Table does not exist"]}}, 422)
        dataset_id = self._next_dataset
        self._next_dataset += 1
        columns = [self._column(name) for name in self.view_columns(view_id)]
        self.datasets[dataset_id] = {
            "table_name": name,
            "sql": body["sql"],
            "view": view_id,
            "columns": columns,
        }
        return self._json(
            {
                "data": {"id": dataset_id, "columns": [dict(c) for c in columns]},
                "id": dataset_id,
                "result": {"table_name": name, "sql": body["sql"], "schema": "bi_data"},
            },
            201,
        )

    def _column(self, name: str) -> dict[str, Any]:
        column = {"id": self._next_column, "column_name": name, "verbose_name": None}
        self._next_column += 1
        return column

    def _refresh_dataset(self, dataset_id: int, dataset: dict[str, Any]) -> httpx.Response:
        if dataset["view"] in self.missing_views:
            return self._json({"message": "Dataset could not be refreshed"}, 422)
        wanted = self.view_columns(dataset["view"])
        kept = [c for c in dataset["columns"] if c["column_name"] in wanted]
        have = {c["column_name"] for c in kept}
        kept += [self._column(n) for n in wanted if n not in have]
        dataset["columns"] = kept
        return self._json({"message": "OK"})

    def _put(
        self, dataset_id: int, dataset: dict[str, Any], body: dict[str, Any]
    ) -> httpx.Response:
        columns = body.get("columns")
        if columns is not None:
            existing = {c["id"]: c for c in dataset["columns"]}
            if any(c.get("id") not in existing for c in columns):
                return self._json(
                    {"message": {"columns": ["One or more columns do not exist"]}}, 422
                )
            # 교체: 보낸 열만 남는다(빠진 열은 지워진다).
            dataset["columns"] = [
                {
                    "id": c["id"],
                    "column_name": existing[c["id"]]["column_name"],
                    "verbose_name": c.get("verbose_name"),
                }
                for c in columns
            ]
        name = body.get("table_name")
        if name is not None:
            if any(i != dataset_id and d["table_name"] == name for i, d in self.datasets.items()):
                return self._json({"message": {"table": ["already exists"]}}, 422)
            dataset["table_name"] = name
        return self._json({"id": dataset_id, "result": {"table_name": dataset["table_name"]}})


def new_fake(
    *, service=("bi_service", "svc-pw-SECRET-1"), issuer=("bi_guest_issuer", "iss-pw-SECRET-2")
):
    fake = FakeSuperset()
    fake.add_account(service[0], service[1], "service")
    fake.add_account(issuer[0], issuer[1], "issuer")
    return fake


def unquoted(value: str) -> str:
    return unquote(value)
