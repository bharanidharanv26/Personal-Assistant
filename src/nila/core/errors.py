class DomainError(Exception):
    def __init__(self, status: int, detail: str, resource_id: str | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.resource_id = resource_id
