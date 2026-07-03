"""Order controller — paper trading order management with safety gates.

Wraps the OrderBackend with a **defense-in-depth** ``confirmed`` check
at the controller level *in addition to* the backend-level check.
"""

from typing import Any

from core.services.backends import build_order_backend
from core.services.backends.base import OrderBackend
from core.services.dom_utils import DomUtils
from core.services.errors import OrderSubmissionBlocked


class TVOrderController:
    """Paper trading order management.

    **Safety:** ``place()`` requires ``confirmed=True`` at the controller
    level (defense in depth — the backend also checks).  Never call with
    ``confirmed=False`` expecting it to silently pass through.
    """

    def __init__(self, cdp, recon: dict, allow_unverified: bool = False):
        self._cdp = cdp
        self._dom = DomUtils(cdp)
        self._backend: OrderBackend = build_order_backend(
            recon, cdp, self._dom, allow_unverified
        )

    async def place(self, symbol: str, side: str, size: float,
                    order_type: str = "market",
                    sl: float | None = None,
                    tp: float | None = None,
                    confirmed: bool = False) -> str:
        """Submit a paper order.

        *confirmed* must be explicitly ``True`` — this is NOT a
        convenience default.  See §2.2 safety note in the build spec.
        """
        if not confirmed:
            raise OrderSubmissionBlocked(
                "order_place requires confirmed=True — "
                "this is a safety gate at the controller level. "
                "Pass confirmed=True to proceed.",
                details={"symbol": symbol, "side": side, "size": size},
            )
        return await self._backend.place(
            symbol, side, size, order_type, sl, tp, confirmed=True,
        )

    async def modify(self, order_id: str,
                     size: float | None = None,
                     sl: float | None = None,
                     tp: float | None = None) -> None:
        """Modify a working order's size, SL, or TP."""
        await self._backend.modify(order_id, size, sl, tp)

    async def cancel(self, order_id: str) -> None:
        """Cancel a working order."""
        await self._backend.cancel(order_id)

    async def status(self) -> list[dict[str, Any]]:
        """Read open positions and working orders."""
        return await self._backend.status()

    async def health_check(self) -> dict[str, Any]:
        return {"order": await self._backend.health_check()}
