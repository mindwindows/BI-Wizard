"""Superset REST 클라이언트(`httpx` 동기, 08 §2-2·§4).

- 계정 하나당 `SupersetSession` 하나(쿠키 항아리·접근/갱신 토큰·CSRF 토큰). 서비스 계정(등록)과 발급
  전용 계정(입장권)은 서로 다른 인스턴스다. 토큰은 **메모리에만** 두고 프로세스를 다시 띄우면 새로
  로그인한다.
- 요청 주소는 `<내부 주소 상수><SUPERSET_APP_ROOT>/api/v1/...`이다(AP-12). 환경변수로 주소를 받지
  않는다. `trust_env=False`라 프록시 환경변수를 타지 않고, 리다이렉트를 따라가지 않으며, 자동
  재시도는 하지 않는다. 예외 두 가지만 한 번 다시 보낸다: 401(접근 토큰 만료: 갱신 뒤)과 CSRF 400
  (토큰을 다시 받은 뒤). 멱등 GET의 연결 끊김도 한 번 다시 보낸다.
- 401일 때만 토큰을 갱신한다. 400은 CSRF 오류와 입장권 훅 거부가 같은 상태 코드이므로 본문에
  `CSRF`가 있을 때만 CSRF로 보고 다시 시도한다(프로브 P-3).
- **오류에는 사유 코드만 담는다.** 응답 본문·URL·토큰·비밀번호·쿠키는 로그, 예외 메시지, 호출한 쪽
  어디에도 넘기지 않는다(422 중복 메시지에는 URL 인코딩된 이름이 들어 있다). `httpx`·`httpcore`
  로거는 요청 URL을 INFO로 남기므로 WARNING으로 고정한다.
- **`httpx.HTTPError`가 아닌 예외**(`InvalidURL`, `CookieConflict` 등)도 이 파일의 호출 경계에서
  `SupersetRejected("INTERNAL")`로 바꾼다. 로그에는 **예외 클래스 이름만** 남기고(메시지·URL 없음)
  원인 예외는 붙이지 않는다(`from None`). 전역 500 핸들러까지 올라가지 않는다.
- 로그인이 거부(`AUTH_FAILED`)되면 `LOGIN_RETRY_BACKOFF_SECONDS` 동안 로그인을 다시 시도하지 않고
  곧바로 같은 거부를 돌려준다(틀린 비밀번호로 사용자 요청마다 로그인을 퍼붓지 않는다).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Collection
from typing import Any

import httpx
from pydantic import SecretStr

from app.superset.constants import DATABASE_NAME, HEALTH_TIMEOUT, LOGIN_RETRY_BACKOFF_SECONDS
from app.superset.errors import SupersetRejected, SupersetUnavailable

for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

_API = "/api/v1"


def rison_string(value: str) -> str:
    """Rison 글자 값: 작은따옴표로 감싸고 `!`는 `!!`, `'`는 `!'`로 이스케이프한다(프로브 P-2)."""
    return "'" + value.replace("!", "!!").replace("'", "!'") + "'"


def _is_csrf_error(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        return "CSRF" in response.text
    except Exception:  # pragma: no cover - 본문을 못 읽으면 CSRF 오류로 보지 않는다
        return False


class SupersetSession:
    """한 계정의 로그인 상태를 가진 HTTP 세션."""

    def __init__(
        self,
        *,
        root: str,
        base_url: str,
        username: str,
        password: SecretStr,
        timeout: httpx.Timeout,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        login_backoff: float = LOGIN_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self._clock = clock
        self._login_backoff = login_backoff
        self._login_blocked_until: float | None = None
        self._origin = base_url.rstrip("/")
        self._root = root
        self._username = username
        self._password = password
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=8),
        )
        self._lock = threading.RLock()
        self._access: str | None = None
        self._refresh: str | None = None
        self._csrf: str | None = None

    def close(self) -> None:
        self._client.close()

    def _url(self, path: str) -> str:
        return f"{self._origin}{self._root}{path}"

    @staticmethod
    def _wrap(error: httpx.HTTPError) -> SupersetUnavailable | SupersetRejected:
        """전송 계층 오류를 사유 코드로 바꾼다(원인 예외는 붙이지 않는다: 메시지에 URL이 있다)."""
        if isinstance(error, httpx.TimeoutException):
            return SupersetUnavailable("UNAVAILABLE_TIMEOUT")
        if isinstance(error, httpx.TransportError):
            return SupersetUnavailable("UNAVAILABLE_CONNECT")
        return SupersetRejected("BAD_RESPONSE")

    @staticmethod
    def _unexpected(error: Exception) -> SupersetRejected:
        """`httpx.HTTPError`가 아닌 예외. 클래스 이름만 남기고 사유 코드로 바꾼다."""
        logger.error("Superset 호출 중 예기치 않은 예외: %s", type(error).__name__)
        return SupersetRejected("INTERNAL")

    def _exchange(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """HTTP 요청 한 번. 모든 예외를 사유 코드 예외로 바꾼다(원인 예외는 붙이지 않는다)."""
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise self._wrap(error) from None
        except Exception as error:
            raise self._unexpected(error) from None

    # --- 로그인·토큰 ---

    def _login(self) -> None:
        """접근/갱신 토큰을 새로 받는다(`_lock` 안에서 부른다).

        거부(`AUTH_FAILED`) 뒤 `LOGIN_RETRY_BACKOFF_SECONDS` 동안은 Superset을 부르지 않고 바로 같은
        거부를 낸다.
        """
        if self._login_blocked_until is not None:
            if self._clock() < self._login_blocked_until:
                raise SupersetRejected("AUTH_FAILED")
            self._login_blocked_until = None
        body = {
            "username": self._username,
            "password": self._password.get_secret_value(),
            "provider": "db",
            "refresh": True,
        }
        try:
            response = self._exchange("POST", self._url(f"{_API}/security/login"), json=body)
        finally:
            body.clear()
        if response.status_code >= 500:
            raise SupersetUnavailable("UNAVAILABLE_5XX")
        if response.status_code != 200:
            self._login_blocked_until = self._clock() + self._login_backoff
            raise SupersetRejected("AUTH_FAILED")
        data = self._json(response)
        access, refresh = data.get("access_token"), data.get("refresh_token")
        if not isinstance(access, str) or not access:
            raise SupersetRejected("BAD_RESPONSE")
        self._access = access
        self._refresh = refresh if isinstance(refresh, str) and refresh else None
        self._csrf = None
        self._login_blocked_until = None

    def _renew_access(self, used_token: str | None) -> None:
        """401 뒤에 접근 토큰을 갱신한다. 다른 스레드가 이미 갱신했으면 다시 하지 않는다."""
        with self._lock:
            if self._access is not None and self._access != used_token:
                return
            if self._refresh is not None:
                response = self._exchange(
                    "POST",
                    self._url(f"{_API}/security/refresh"),
                    headers={"Authorization": f"Bearer {self._refresh}"},
                )
                if response.status_code >= 500:
                    raise SupersetUnavailable("UNAVAILABLE_5XX")
                if response.status_code == 200:
                    access = self._json(response).get("access_token")
                    if isinstance(access, str) and access:
                        self._access = access
                        return
            self._login()

    def _ensure_login(self) -> str:
        with self._lock:
            if self._access is None:
                self._login()
            assert self._access is not None  # noqa: S101 - _login이 채웠다
            return self._access

    def _ensure_csrf(self, access: str) -> tuple[str, str]:
        """CSRF 토큰과 그 호출에 쓴 접근 토큰을 돌려준다.

        접근 토큰이 만료돼 401이면 갱신한 뒤 한 번 더 받는다(캐시된 CSRF가 없을 때
        첫 호출이 쓰기여도 만료된 로그인에서 막히지 않게).
        """
        with self._lock:
            if self._csrf is not None:
                return self._csrf, access
            for attempt in range(2):
                response = self._exchange(
                    "GET",
                    self._url(f"{_API}/security/csrf_token/"),
                    headers={"Authorization": f"Bearer {access}"},
                )
                if response.status_code >= 500:
                    raise SupersetUnavailable("UNAVAILABLE_5XX")
                if response.status_code == 401 and attempt == 0:
                    self._renew_access(access)
                    assert self._access is not None  # noqa: S101 - _renew_access가 채웠다
                    access = self._access
                    continue
                if response.status_code in (401, 403):
                    raise SupersetRejected("AUTH_FAILED")
                if response.status_code != 200:
                    raise SupersetRejected("BAD_RESPONSE")
                token = self._json(response).get("result")
                if not isinstance(token, str) or not token:
                    raise SupersetRejected("BAD_RESPONSE")
                self._csrf = token
                return token, access
        raise SupersetRejected("AUTH_FAILED")  # pragma: no cover

    # --- 요청 ---

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except Exception:  # JSON이 아니거나 본문을 읽을 수 없다(원인 예외는 붙이지 않는다)
            raise SupersetRejected("BAD_RESPONSE") from None
        if not isinstance(data, dict):
            raise SupersetRejected("BAD_RESPONSE")
        return data

    def _send_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None,
        json: Any,
        csrf: bool,
    ) -> tuple[httpx.Response, str]:
        access = self._ensure_login()
        csrf_token = None
        if csrf:
            csrf_token, access = self._ensure_csrf(access)
        headers = {"Authorization": f"Bearer {access}"}
        if csrf_token is not None:
            headers["X-CSRFToken"] = csrf_token
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = self._client.request(
                    method, self._url(path), params=params, json=json, headers=headers
                )
            except httpx.RemoteProtocolError:
                if attempt + 1 < attempts:  # 멱등 GET의 끊긴 연결은 한 번 더 보낸다
                    continue
                raise SupersetUnavailable("UNAVAILABLE_CONNECT") from None
            except httpx.HTTPError as error:
                raise self._wrap(error) from None
            except Exception as error:
                raise self._unexpected(error) from None
            return response, access
        raise SupersetUnavailable("UNAVAILABLE_CONNECT")  # pragma: no cover

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        csrf: bool = False,
        accept: Collection[int] = (),
        forbidden_code: str = "AUTH_FAILED",
    ) -> httpx.Response:
        """요청을 보내고 성공(2xx) 또는 `accept`에 든 상태의 응답을 돌려준다. 그 밖에는 예외다.

        예외에는 사유 코드만 있다: 연결·시간 초과·5xx는 `SupersetUnavailable`, 그 밖은
        `SupersetRejected`(401은 `AUTH_FAILED`, 403은 `forbidden_code`, 나머지는 `REJECTED_<상태>`).
        """
        response, used = self._send_once(method, path, params=params, json=json, csrf=csrf)
        if response.status_code == 401:
            self._renew_access(used)
            response, used = self._send_once(method, path, params=params, json=json, csrf=csrf)
        elif csrf and _is_csrf_error(response):
            with self._lock:
                self._csrf = None
            response, used = self._send_once(method, path, params=params, json=json, csrf=csrf)
        status = response.status_code
        if 200 <= status < 300 or status in accept:
            return response
        if status >= 500:
            raise SupersetUnavailable("UNAVAILABLE_5XX")
        if status == 401:
            raise SupersetRejected("AUTH_FAILED")
        if status == 403:
            raise SupersetRejected(forbidden_code)
        raise SupersetRejected(f"REJECTED_{status}")

    def json(self, response: httpx.Response) -> dict[str, Any]:
        """응답 본문을 사전으로 읽는다. 형식이 다르면 `BAD_RESPONSE`."""
        return self._json(response)

    def health(self) -> bool:
        """`{root}/health`가 200인가(인증 없음, 프로브 P-6). 연결 오류는 거짓이다."""
        try:
            response = self._client.get(self._url("/health"), timeout=HEALTH_TIMEOUT)
        except httpx.HTTPError:
            return False
        except Exception as error:
            self._unexpected(error)  # 클래스 이름만 기록한다
            return False
        return response.status_code == 200


class DatasetApi:
    """서비스 계정의 데이터셋 API(08 §2-1). 응답은 필요한 필드만 뽑아 돌려준다."""

    def __init__(self, session: SupersetSession) -> None:
        self._s = session
        self._database_id: int | None = None

    def forget_database_id(self) -> None:
        self._database_id = None

    def database_id(self) -> int:
        """업무 데이터 연결의 번호. 이름으로 조회해 캐시한다(번호는 환경마다 다르다, 프로브 P-1)."""
        if self._database_id is not None:
            return self._database_id
        response = self._s.request("GET", f"{_API}/dataset/related/database")
        result = self._s.json(response).get("result")
        if isinstance(result, list):
            for item in result:
                if (
                    isinstance(item, dict)
                    and item.get("text") == DATABASE_NAME
                    and isinstance(item.get("value"), int)
                    and not isinstance(item.get("value"), bool)
                ):
                    self._database_id = item["value"]
                    return item["value"]
        raise SupersetRejected("DB_NOT_FOUND")

    def _find(self, filters: list[tuple[str, str]]) -> list[dict[str, Any]]:
        terms = ",".join(
            f"(col:{col},opr:eq,value:{rison_string(value)})" for col, value in filters
        )
        q = f"(filters:!({terms}),columns:!(id,table_name,sql,schema),page_size:20)"
        response = self._s.request("GET", f"{_API}/dataset/", params={"q": q})
        result = self._s.json(response).get("result")
        if not isinstance(result, list):
            raise SupersetRejected("BAD_RESPONSE")
        return [
            item for item in result if isinstance(item, dict) and isinstance(item.get("id"), int)
        ]

    def find_by_sql(self, sql: str, schema: str) -> list[dict[str, Any]]:
        return self._find([("sql", sql), ("schema", schema)])

    def find_by_name(self, name: str, schema: str) -> list[dict[str, Any]]:
        return self._find([("table_name", name), ("schema", schema)])

    def get(self, dataset_id: int) -> dict[str, Any] | None:
        """데이터셋 하나. 없으면 None. `{id, table_name, sql, database_name, columns[{id,
        column_name,
        verbose_name}]}`."""
        response = self._s.request(
            "GET",
            f"{_API}/dataset/{dataset_id}",
            accept=(404,),
            forbidden_code="NOT_OWNER",
        )
        if response.status_code == 404:
            return None
        result = self._s.json(response).get("result")
        if not isinstance(result, dict):
            raise SupersetRejected("BAD_RESPONSE")
        columns = []
        for column in result.get("columns") or []:
            if (
                not isinstance(column, dict)
                or not isinstance(column.get("id"), int)
                or not isinstance(column.get("column_name"), str)
            ):
                raise SupersetRejected("BAD_RESPONSE")
            verbose = column.get("verbose_name")
            columns.append(
                {
                    "id": column["id"],
                    "column_name": column["column_name"],
                    "verbose_name": verbose if isinstance(verbose, str) else None,
                }
            )
        database = result.get("database")
        return {
            "id": dataset_id,
            "table_name": result.get("table_name"),
            "sql": result.get("sql"),
            "database_name": database.get("database_name") if isinstance(database, dict) else None,
            "columns": columns,
        }

    def create(self, *, database_id: int, schema: str, name: str, sql: str) -> int | None:
        """가상 데이터셋을 만든다. 같은 이름이 이미 있으면 None(중복 422), 아니면 새 번호."""
        response = self._s.request(
            "POST",
            f"{_API}/dataset/",
            json={"database": database_id, "schema": schema, "table_name": name, "sql": sql},
            csrf=True,
            accept=(422,),
        )
        if response.status_code == 422:
            # 응답 본문은 쓰지 않는다. `table` 키가 있으면 이름 중복이다(메시지에는 URL 인코딩된
            # 이름이
            # 들어 있어 로그·`last_error`에 옮기지 않는다).
            message = self._s.json(response).get("message")
            if isinstance(message, dict) and "table" in message:
                return None
            self.forget_database_id()
            raise SupersetRejected("REJECTED_422")
        new_id = self._s.json(response).get("id")
        if not isinstance(new_id, int) or isinstance(new_id, bool):
            raise SupersetRejected("BAD_RESPONSE")
        return new_id

    def refresh(self, dataset_id: int) -> None:
        """뷰의 열 변화를 반영한다. 뷰가 없으면 원인 없는 422(`VIEW_MISSING`)."""
        response = self._s.request(
            "PUT",
            f"{_API}/dataset/{dataset_id}/refresh",
            csrf=True,
            accept=(422,),
            forbidden_code="NOT_OWNER",
        )
        if response.status_code == 422:
            raise SupersetRejected("VIEW_MISSING")

    def put_names(
        self,
        dataset_id: int,
        *,
        table_name: str,
        columns: list[dict[str, Any]],
        labels: dict[str, str],
    ) -> bool:
        """이름과 **전체 열**의 표시 이름을 갱신한다(03c A-27: `columns`는 병합이 아니라 교체).

        `columns`는 방금 읽은 열 전체이고, 이 함수는 그 모든 열을
        `{id, column_name, verbose_name}`로 다시 보낸다(일부만 보내는 경로가 없다).
        `labels`에 있는 열만 표시 이름을 바꾸고 나머지는 읽은 값을 그대로 보낸다. 열이 하나도
        없으면 보내지 않는다(빈 목록은 모든 열을 지운다). 돌려주는 값은 "열이 없다는 422"
        (재조회 뒤 한 번 더 시도할 수 있음)이면 False다.
        """
        if not columns:
            raise SupersetRejected("BAD_RESPONSE")
        body_columns = [
            {
                "id": column["id"],
                "column_name": column["column_name"],
                "verbose_name": labels.get(column["column_name"], column["verbose_name"]),
            }
            for column in columns
        ]
        response = self._s.request(
            "PUT",
            f"{_API}/dataset/{dataset_id}",
            json={"table_name": table_name, "columns": body_columns},
            csrf=True,
            accept=(422,),
            forbidden_code="NOT_OWNER",
        )
        if response.status_code == 422:
            message = self._s.json(response).get("message")
            if isinstance(message, dict) and "columns" in message:
                return False
            raise SupersetRejected("REJECTED_422")
        return True
