"""
Stub that replaces EnvironmentService.create_environment to create DB records
without Docker. Used for agent creation tests.
"""
from app.models.agent import Agent
from app.models.environment import AgentEnvironment


async def stub_create_environment(
    session, agent_id, data, user, auto_start=False, source_environment_id=None
):
    """Create environment DB record as running + active. No Docker."""
    env = AgentEnvironment(
        agent_id=agent_id,
        env_name=data.env_name,
        env_version=data.env_version,
        instance_name=data.instance_name,
        type="docker",
        status="running",
        is_active=True,
        config={},
    )
    session.add(env)
    session.commit()
    session.refresh(env)

    agent = session.get(Agent, agent_id)
    agent.active_environment_id = env.id
    session.add(agent)
    session.commit()
    session.refresh(env)
    return env
