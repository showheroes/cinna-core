"""
App MCP Routing Service — determines which agent should handle a message.

Routing priority:
  1. Pattern matching (fnmatch-based glob patterns)
  2. AI classification (LLM picks the best agent from trigger prompts)
  3. Return None if no match found
"""
import fnmatch
import logging
import uuid
from dataclasses import dataclass

from sqlmodel import Session as DBSession

from app.services.app_mcp.app_agent_route_service import (
    AppAgentRouteService,
    EffectiveRoute,
)

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result of routing a message to an agent."""

    agent_id: uuid.UUID
    agent_name: str
    session_mode: str
    route_id: uuid.UUID
    route_source: str  # "admin" | "user"
    match_method: str  # "pattern" | "ai" | "only_one"


class AppMCPRoutingService:
    """Routes MCP messages to the appropriate agent."""

    @staticmethod
    def route_message(
        db_session: DBSession,
        user_id: uuid.UUID,
        message: str,
        channel: str = "app_mcp",
    ) -> RoutingResult | None:
        """Determine which agent should handle a message.

        1. Get effective routes for user.
        2. Try pattern matching.
        3. Fall back to AI classification.

        Returns RoutingResult or None if routing fails.
        """
        effective_routes = AppAgentRouteService.get_effective_routes_for_user(
            db_session=db_session,
            user_id=user_id,
            channel=channel,
        )

        if not effective_routes:
            logger.debug("No effective routes for user %s", user_id)
            return None

        # If only one route, use it directly (no need to classify)
        if len(effective_routes) == 1:
            route = effective_routes[0]
            return RoutingResult(
                agent_id=route.agent_id,
                agent_name=route.agent_name,
                session_mode=route.session_mode,
                route_id=route.route_id,
                route_source=route.source,
                match_method="only_one",
            )

        # 1. Try pattern matching
        matched = AppMCPRoutingService._try_pattern_match(message, effective_routes)
        if matched:
            return RoutingResult(
                agent_id=matched.agent_id,
                agent_name=matched.agent_name,
                session_mode=matched.session_mode,
                route_id=matched.route_id,
                route_source=matched.source,
                match_method="pattern",
            )

        # 2. Fall back to AI classification
        ai_matched = AppMCPRoutingService._ai_classify(message, effective_routes)
        if ai_matched:
            return RoutingResult(
                agent_id=ai_matched.agent_id,
                agent_name=ai_matched.agent_name,
                session_mode=ai_matched.session_mode,
                route_id=ai_matched.route_id,
                route_source=ai_matched.source,
                match_method="ai",
            )

        logger.debug("No route matched for message (user=%s)", user_id)
        return None

    @staticmethod
    def _try_pattern_match(
        message: str,
        routes: list[EffectiveRoute],
    ) -> EffectiveRoute | None:
        """Try each route's message_patterns against the message using fnmatch.

        Patterns are newline-separated glob-style strings (e.g. 'sign this document *').
        Returns the first matching route or None.
        """
        message_lower = message.lower()
        for route in routes:
            if not route.message_patterns:
                continue
            patterns = [
                p.strip()
                for p in route.message_patterns.splitlines()
                if p.strip()
            ]
            for pattern in patterns:
                if fnmatch.fnmatch(message_lower, pattern.lower()):
                    logger.debug(
                        "Pattern match: route=%s pattern=%r message=%r",
                        route.route_id,
                        pattern,
                        message[:80],
                    )
                    return route
        return None

    @staticmethod
    def _ai_classify(
        message: str,
        routes: list[EffectiveRoute],
    ) -> EffectiveRoute | None:
        """Call AI function to classify message against available routes.

        Builds a list of agent dicts with trigger_prompt descriptions
        and asks the LLM to pick the best match.
        Returns matched route or None.
        """
        from app.services.ai_functions.ai_functions_service import AIFunctionsService

        available_agents = [
            {
                "id": str(route.agent_id),
                "name": route.agent_name,
                "trigger_prompt": route.trigger_prompt,
            }
            for route in routes
        ]

        agent_id_str = AIFunctionsService.route_to_agent(
            message=message,
            available_agents=available_agents,
        )

        if not agent_id_str:
            return None

        # Find the matching route
        try:
            agent_id = uuid.UUID(agent_id_str)
        except ValueError:
            logger.warning("AI router returned invalid UUID: %r", agent_id_str)
            return None

        for route in routes:
            if route.agent_id == agent_id:
                return route

        logger.warning("AI router returned agent_id %s not in effective routes", agent_id_str)
        return None
