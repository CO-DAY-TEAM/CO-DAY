class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class GitHubError(ServiceError):
    def __init__(self, status: int, retryable: bool = False):
        super().__init__(
            "github_error",
            "GitHub 요청을 처리하지 못했습니다. 권한과 연결 상태를 확인해 주세요.",
            502,
        )
        self.github_status = status
        self.retryable = retryable


class Stopped(ServiceError):
    pass
