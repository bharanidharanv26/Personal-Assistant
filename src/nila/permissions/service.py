from nila.core.config import Settings
from nila.core.schemas import ApprovalView, ConsentRequest, ConsentView
from nila.storage.repositories import ApprovalRepository, ConsentRepository


class PermissionService:
    def __init__(
        self, settings: Settings, approvals: ApprovalRepository,
        consents: ConsentRepository,
    ) -> None:
        self.settings = settings
        self.approvals = approvals
        self.consents = consents

    def approve(self, action_id: str, digest: str) -> ApprovalView:
        return self.approvals.approve(action_id, digest, self.settings.approval_ttl_seconds)

    def refuse(self, action_id: str, *, revoke: bool = False) -> None:
        self.approvals.refuse(action_id, revoke=revoke)

    def grant_consent(self, request: ConsentRequest) -> ConsentView:
        return self.consents.grant(request)

    def list_consents(self, limit: int = 100) -> list[ConsentView]:
        return self.consents.list(limit)

    def revoke_consent(self, consent_id: str) -> ConsentView:
        return self.consents.revoke(consent_id)
