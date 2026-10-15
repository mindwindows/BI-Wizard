import { configure } from "@testing-library/react";

// CPU 부하에서 findBy*/waitFor의 기본 1000ms 대기가 모자라 흔들리는 일을 막는다(시험 실행에만 영향).
configure({ asyncUtilTimeout: 10000 });
