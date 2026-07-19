from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SSOIdentity:
    subject: str
    email: str
    tenant_slug: str


class SSOProvider(ABC):
    """Interface every SSO/SAML integration plugs into. Phase 0 only
    scaffolds this — no real identity provider is wired up yet, since
    that needs a per-tenant IdP configuration (ACS URL, certificates)
    that doesn't exist until a real enterprise customer sets one up."""

    @abstractmethod
    def authenticate(self, assertion_or_token: str) -> SSOIdentity: ...


class SAMLProvider(SSOProvider):
    def authenticate(self, assertion_or_token: str) -> SSOIdentity:
        raise NotImplementedError(
            "SAML SSO is not yet configured. Wire up a per-tenant IdP "
            "(ACS URL, certificate, entity ID) before enabling this."
        )
