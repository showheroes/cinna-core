# Management of Organisations / Teams / Users

Reference to business logic for agent sessions: docs/agent-sessions/business_logic.md

## Executive Summary

This document defines the organizational structure, permission model, and resource sharing mechanisms for the multi-tenant agent platform.

**Key Concepts:**
- **Organizations**: Top-level containers for teams, users, and resources. Users can be members of multiple orgs and switch contexts.
- **Teams**: Permission management groups within orgs (max 2-level nesting). Teams provide access, they don't own resources.
- **Workspaces**: UI-only organization folders (no permissions, no data isolation, no membership).
- **Replicant Agents**: Private copies of shared agents. Updates queued and rolled out during off-hours or manually.
- **Credentials**: Three types - private (user's personal), org_private (user's within org, admin-managed), org_shared (agent-only, auto-integrated).
- **AI Credentials**: Per-user tracking for billing. Private mode uses user's credentials; org mode uses org-assigned credentials.

**Core Design Principles:**
- RBAC with allow-only rules (no deny), most permissive permission wins
- No cross-org collaboration - agents stay within org boundaries
- Privacy-first: admins cannot see user conversation sessions
- Hard delete only (initially) - no soft delete or grace periods
- Org context: org owns all resources, users cannot export when leaving
- Forking allowed for builders: copies prompts but not credentials

**See Implementation Notes section for detailed priorities and explicitly excluded features.**

## Sharing Logic

### Agents sharing

Specifics of agents sharing requires different approach to how agent can be used.

Conversation mode assumes no modifications to prompts, just use to execute certain workflow following instructions.
Example: "Meeting Booking Agent" - knows how to book meetings in the organisations, what APIs to access, etc.

Building (full access) mode assumes that user can modify anything about the agent, it's prompts, etc.
In this case user completely owns the agent.

Although, we have scenarios when one user owns the agents and builds it ('builder'), and another user uses it privately ('consumer').
But at the same time, 'consumer' should be able to utilize this agent privately.

User story:
- Company's 'builder' creates "Meeting Booking Agent".
- This agent gets shared with the team "Sales".
- Now sales manager can send a message to that agent to book a meeting in the office with a client.
- Agent would follow procedures defined by the 'builder', but will use credentials of that particular 'consumer', like his email, name and access to Calendar API.

We can call such temporary copies of the original agent a 'replicant agent'.
Replicant preserves their own agent-env details (shared credentials, created files, uploads, sessions, etc.),
but internals (agent-env APIs, internal services, libraries, system prompts) are managed by the builder.
Builder at any time can make changes to the agent and force an update across replicants.

This approach would allow to make up-to-date agents available across organisation without complicated update processes.

Using 'replicants' assumes that access to the internal in this scenario is also limited and only conversation mode is available.

#### Replicant Lifecycle

**Creation:**
- Replicant is automatically created when a consumer first accesses a shared agent
- Replicant inherits all agent configuration from the original agent (system prompts, APIs, libraries)
- Replicant maintains its own isolated state (credentials, files, sessions, conversation history)

**Updates:**
- Builder can push updates to the original agent
- Update is placed in a queue and shown in the replicant-agent UI
- Updates are automatically rolled out during night hours or when agent-env goes into sleep state (not actively used)
- Users can manually trigger update from the replicant config UI
- Each replicant has 'Updates: automatic / manual' option (default: automatic)
- Version tracking allows consumers to see when their replicant was last synced

**Deletion:**
- When consumer loses access (removed from team, leaves org), their replicant is marked for deletion
- Replicant data (sessions, files) is retained for configurable period (e.g., 30 days) for recovery
- Builder deleting original agent marks all replicants for deletion with notification to consumers
- Consumer can manually delete their replicant while retaining team access

**Forking:**
- Only users with builder permissions (can build agents) can fork a replicant
- Forking creates a fully independent agent owned by the consumer
- Forked agent copies: system prompts and agent configuration
- Forked agent does NOT copy: credentials, handover config, scheduler config
- Builder has visibility into all forks via a separate fork-overview list
- This allows experimentation without affecting shared agent

### Credentials sharing

Credentials could be managed in the following way:
- 'private' - in the private space as private credentials, for example: private email account 
- 'org_private' - in the org space as private credential existing only inside this organisation, for example: API access to corporate ERP as an employee of that organisation (private, but within org)
- 'org_shared' - in the org space as shared credential, for example: access to external service under organisation's name (external org account) 

#### Credentials 'org_private'

They can be managed by the org administrators.
For example: new user joins organisation and to avoid complicated setup, API credentials to access company's resources created for him by admins.
These credentials belong to a user and available to him for management, but also managed by admins.
That's a special RBAC permission 'manage_org_private_credentials'.

**Lifecycle:**
- Created by: user themselves OR org admin on behalf of user
- Modified by: credential owner OR org admin with 'manage_org_private_credentials'
- Deleted by: credential owner OR org admin
- When user leaves org: credentials are revoked and archived for audit purposes

**OAuth Credentials (org_private):**
- Org admin can create OAuth credential placeholder for user
- Actual setup of refresh/access tokens must be done by the user
- No one from org has access to credential internals (values)
- Org specifies what needs to be created for which agents, but user completes actual setup
- Before message sent to agent-env, access token expiration is checked
- If expired: system automatically refreshes token → syncs to agent-env → sends message
- OAuth credentials always use server-side flow with refresh token

#### Credentials 'org_shared'

They are managed centrally by org admins and can be used (read) by singular users (teams) they are shared with,
but these credentials can only be modified by users who have such permission.

**Important:** All org_shared credentials are agent-only (not directly accessible to users). They come pre-integrated inside shared agent replicants. Users don't discover or select these credentials themselves - they're automatically available to the replicant.

**Lifecycle:**
- Created by: org admin OR users with 'manage_org_shared_credentials' permission
- Used by: integrated into shared agents, automatically available in replicants
- Modified by: org admin OR users with 'manage_org_shared_credentials' permission
- Deleted by: org admin OR credential creator
- Audit trail: all usage of org_shared credentials is logged with timestamp and user info

**Rotation & Expiration:**
- Org admins can set expiration dates on credentials
- System notifies admins before credential expiration
- Expired credentials are automatically disabled but retained for audit

**Discovery:**
- Users don't browse or select org_shared credentials
- If user needs credentials separately, org provides via password manager
- User creates credential record themselves, making it org_private

### AI Credentials (Billing & Usage Tracking)

AI credentials determine which LLM API account is used for agent operations and enable usage tracking.

**Private Mode:**
- Each user account has private AI credentials in their configuration
- Used when working in private mode (no org context)
- User pays for their own agent usage

**Organization Mode:**
- AI credentials assigned by org admins to each member
- Each member has their own org-assigned AI credentials to track usage at user level
- When agent-env is built in org context, it uses org-assigned AI credentials
- When using replicant agents, consumer's org-assigned AI credentials are used
- This allows org to track which users consume resources and how much

**Cross-Organization:**
- Each user always has their own AI credentials
- When context switches to org, org-assigned credentials are used
- If consumer is in different org (not applicable - no cross-org sharing), they would use their own org's AI credentials

### Knowledge Source Sharing

Knowledge sources are shared as regular entities: either to a user directly or to a team.
They can be private or org managed.
Once user is having access to read certain knowledge source, this knowledge source becomes available to all of his agents.

**Types of Knowledge Sources:**
- GIT Repositories (containing files for RAG)

**Sharing Levels:**
- Private: only owner has access
- Org-wide: all org members can read
- Team-specific: specific teams can read
- User-specific: specific users can read

**Access Control:**
- Read: can use knowledge source in agents
- Write: can update/modify knowledge source content
- Manage: can change sharing permissions
- Delete: can remove knowledge source

**Lifecycle:**
- When access is revoked: knowledge source is removed from user's available sources immediately
- When knowledge source is updated: all agents using it automatically get latest version (no notification to agent owners)
- When knowledge source is deleted: it's marked as unavailable in all agents using it

**Note:** For detailed information on knowledge sources, see `docs/agent-sessions/agent_solutions_knowledge_management.md`

## Basic Domain Entities

Reference to the workspaces: docs/user_workspaces_management.md

### Users

Basic entity of accessing resources.
Each user can act as a private account or as a member of an org.
When user acts as a member of an org, entities he creates by default belong to the organisation,
and permissions checked in the space of that organisation, not privately.

Since RBAC eventually checks everything up to a single user, that means that everything what is subject to sharing,
can be managed on the level of single users or teams.

For example: agent can be shared with a user, or all users of specific team.

**User Lifecycle:**

**Account Creation:**
- User signs up with email/password or OAuth (Google)
- Email verification required
- Account starts in private mode (no org affiliation)
- Default private workspace created automatically

**Active User:**
- Can switch between private mode and org contexts
- Can be member of multiple organizations
- Can have different roles in different organizations
- Can create private entities even when working in org context

**User Suspension:**
- Org admins can suspend users within their org (doesn't affect user's private account)
- Suspended user loses access to org resources but data is retained
- Suspended user cannot be tagged in shares or added to teams
- Can be reactivated by org admin

**User Leaving Organization:**
- User can voluntarily leave org (if not the last owner)
- Org admin can remove user from org
- User's private entities remain intact
- User's org_private credentials are revoked and archived
- User's replicant agents are deleted (hard delete)
- User's sessions in org context remain private (admins cannot access)
- Agents created in org context remain with the org (user cannot take them)

**Account Deletion:**
- User can delete their entire account (all orgs and private data)
- Before deletion, user must transfer org ownership or have another owner
- All private data permanently deleted (hard delete, no grace period)
- Org data created by user remains in org ownership
- No data export available when leaving org

### Organisations

Organisations - top level to group teams and users together. 

Details:
- User could belong to an organisation or can be in a 'private mode'.
- User can switch between 'Org mode' and 'private mode'.
- Meaning user's account by default is private, but he can create new or join to other organisations.
- Switching between different orgs or private mode - matter of the current browser window (not permanent).
- Meaning user can have 2 browser windows opened, one for some org and one for private mode.
- Active org (or private mode), similar to the behavior of workspaces, defines what resources are visible and what permissions apply to user actions.

**Organization Lifecycle:**

**Creation:**
- Any user can create unlimited organizations
- Creator automatically becomes first owner
- Default built-in roles are created automatically
- No billing/limits enforced initially (configurable)

**Active Organization:**
- Can have multiple owners for redundancy
- Can have unlimited members (unless plan limits apply)
- Org data is isolated from other orgs
- Each org has its own teams, workspaces, agents, credentials

**Organization Transfer:**
- Ownership can be transferred to another user
- Requires acceptance from new owner
- Original owner can choose to remain as owner or step down to admin

**Organization Deletion:**
- Only owners can delete organization
- Last owner must delete org or promote someone else (no automatic promotion)
- Requires confirmation and password re-entry
- All org data (agents, credentials, sessions, files) permanently deleted (hard delete)
- Users' private data remains intact
- After deletion, org name becomes available for reuse

User stories:

**Scenario 1: Creating Organization**
1. User creates his account
2. User creates Org and becomes org owner
3. Default roles are automatically created (Regular, Experienced, Builder, Admin, Owner)

**Scenario 2: Inviting Existing User**
1. User goes into the list of Org members, clicks "Invite user"
2. User enters email address of another user
3. If user exists in system, invitation is created
4. If user doesn't exist yet, invitation is sent to email (they can accept after signup)
5. In the invitation, org admin specifies: what teams user should join, what role user gets in org
6. Invited user receives notification
7. If user accepts invitation - they join the org; if rejects - invitation marked as rejected
8. Invitations expire after 7 days if not accepted

**Scenario 3: Multi-Organization Work**
1. User is member of "Company A" and "Company B" orgs
2. User opens browser tab, selects "Company A" context
3. User creates agent "Sales Bot" - it belongs to Company A, uses Company A's AI credentials
4. User opens another tab, selects "Company B" context
5. User creates agent "Support Bot" - it belongs to Company B, uses Company B's AI credentials
6. User opens third tab, selects "Private" context
7. User creates agent "Personal Assistant" - it's private, uses user's private AI credentials
8. Note: User cannot share agents across orgs - "Sales Bot" only available to Company A members

### Organisation Roles and RBAC

Serves to manage types of actions available to the user in the context of that Org.

Build-in Roles:
- Regular - can access resources of the org, agents shared with him, create his credentials, private workspaces.
- Experienced - extension to 'Regular', cannot build agents for the org, but can for himself.
- Builder - extension to 'Experienced, can create new and manage existing agents (don't have access to org settings).
- Admin - extension to 'Builder', can manage all agents/environments/users/... in the org, including destructive actions. Cannot create owners.
- Owner - extension to 'Admin', but can delete/modify org. Can assign new owners.

Once new organisation is created, these roles are created by default in that org, but org admin (or owner) can change those,
or create new ones.

Except the 'Owner' role, which is a 'locked' role:
- at least one user should exist with that role
- role cannot be deleted or modified

This is basically RBAC under the hood, with permissions like:
- agent
  - create
  - read
  - update
  - delete
  - share
  - unshare
  - view_all (see all org agents)
  - fork (create independent copy)
  - ...
- credentials
  - create
  - read
  - update
  - delete
  - share
  - manage_org_private_credentials
  - manage_org_shared_credentials
  - ...
- knowledge_source
  - create
  - read
  - update
  - delete
  - share
  - ...
- team
  - create
  - view
  - update
  - delete
  - add_members
  - remove_members
  - ...
- workspace
  - create
  - view
  - update
  - delete
  - manage_org_workspaces
  - ...
- org
  - view_members
  - invite_members
  - remove_members
  - manage_roles
  - view_settings
  - update_settings
  - delete_org
  - ...

Meaning we have default built-in RBAC, and it is applied on org creation, but user can improve that to his needs.

**Permission Inheritance:**
- User's effective permissions = union of all permissions from all their teams + direct role assignment
- RBAC uses only "allow" rules, no "deny" rules
- If any team or role grants a permission, user has that permission (most permissive wins)
- Owner role always has all permissions regardless of team memberships
- No individual resource-level permission overrides (cannot block specific user from shared agent)

**Custom Roles:**
- Org admins can create custom roles beyond built-in ones
- Custom roles are composed of individual permissions
- Custom roles can be assigned to users directly or through teams
- Built-in roles (except Owner) can be cloned and modified

**Permission Evaluation:**
1. Check if user is owner (if yes, allow all)
2. Check user's direct role permissions
3. Check permissions from all user's teams (including nested teams)
4. Combine all permissions (union - any "allow" grants access)
5. Check resource-specific shares (e.g., agent shared directly with user or their team)
6. Allow if any permission source grants access

**Privacy & Admin Boundaries:**
- Org admins can manage users, teams, and agents
- Org admins CANNOT see user conversation sessions
- Sessions belong to individual users and remain private
- Audit logging for GDPR compliance (planned for future)

**Cross-Organization Restrictions:**
- Agents cannot be shared across organization boundaries
- Users from different orgs cannot collaborate on a single agent
- To collaborate on an agent, users must be members of the same org (the org that owns the agent)
- Agents cannot be shared with external users (not part of any org)
- Each org's data is completely isolated

### Workspaces

Workspaces - is a way to organize data and reduce UI clutter.

Details:
- Workspaces are purely UI organization ("folders"), not for permissions or data isolation
- Workspaces do NOT have membership - they're just containers for organizing entities
- To manage group access, use Teams (not Workspaces)
- When org builds an agent, it can assign the agent to an org workspace
- When user receives access to an agent, they see it in that workspace in their UI
- Workspaces can contain agents from multiple teams (e.g., "Finance" workspace with agents for both "Accounting Team" and "Sales Team")
- Cannot share entire workspace with a team - sharing happens at resource level (agent, credential, etc.)
- Workspace can be managed by the user (private mode) or become "Org Workspace" (managed by Org Admins)
- When user switches between context (private / selected org), workspaces for selection are loaded according to the context
- Within context of an org, user can still create private workspaces visible only to them
- User cannot manage org workspaces unless they have permission to do so
- Workspaces are browser window related (2 browser windows can be in different workspaces)
- Mobile app: only a single workspace active at a time
- API access: must provide active workspace and active org in API calls
- Example: User has private workspaces like 'Home Agents', 'Pet-Project Agents'; in org context: 'Office Agents', 'Infrastructure Agents'
- Agents in different workspaces can interact with each other (no isolation) 


### Teams

Teams - always belong to an organisation, it's an org sub-unit that primarily exists for permissions management.
Teams is basically a way to assign certain role to a user through a group.
Since users can be in multiple teams, RBAC permissions check made across all teams and roles assigned to these teams.

**Team Management:**
- Created by: org admin OR users with 'create_team' permission
- Can be nested up to 2 levels (team → subteam, no deeper)
- Permissions always cascade down from parent to child teams
- Team membership can be managed by: org admin OR team managers
- Teams can have managers (users with elevated permissions within team scope)
- Teams provide access to resources, they don't "own" or "assign" resources
- Circular dependencies allowed: Team A can be parent of Team B which has permissions Team A needs (highest permission wins)

**Team Lifecycle:**

**Creation:**
- User with appropriate permission creates team
- Team starts empty (no members)
- Team can be assigned default role for all members

**Active Team:**
- Members can be added/removed
- Team can be assigned to multiple resources (agents, credentials, knowledge sources)
- Team roles can be changed by org admin

**Team Deletion:**
- Only org admin or team creator can delete
- All team shares are revoked
- Members lose permissions granted through this team
- No bulk reassignment of resources (teams only provide access, don't own resources)
- Team data permanently deleted (hard delete)

User stories:

**Scenario 1: Department Team**
1. Org admin creates team "Sales Dept"
2. Admin adds 10 sales team members to the team
3. Builder creates agent "CRM Assistant"
4. Builder shares agent with "Sales Dept" team with "Regular" role
5. All 10 team members can now use "CRM Assistant" in conversation mode
6. New sales hire joins org and is added to "Sales Dept" → automatically gets access to "CRM Assistant"

**Scenario 2: Project Team with Hierarchy**
1. Org admin creates team "Engineering"
2. Org admin creates sub-team "Frontend Team" under "Engineering"
3. Org admin creates sub-team "Backend Team" under "Engineering"
4. Shared credential for company GitHub is shared with "Engineering" team
5. Both "Frontend Team" and "Backend Team" members inherit access to GitHub credential
6. Additional credential for deployment server shared only with "Backend Team"

**Scenario 3: Cross-functional Team**
1. User creates agent "Product Launch Tracker"
2. User shares with multiple teams: "Sales Dept", "Marketing Dept", "Engineering"
3. Each team has different role: Sales=Regular, Marketing=Regular, Engineering=Builder
4. Sales and Marketing can only use agent, Engineering can modify it

---

## Additional User Scenarios

### Scenario: Temporary Contractor Access
1. Org admin invites contractor@example.com to join "ACME Corp"
2. Contractor accepts and joins with "Regular" role
3. Admin adds contractor to temporary team "Q1 Project"
4. Team has access to specific agents and credentials for project
5. After 3 months, admin removes contractor from org
6. Contractor's replicant agents are deleted after 30-day retention
7. Contractor's org_private credentials are revoked
8. Contractor retains their personal account and can still use private mode

### Scenario: Department Reorganization
1. Company merges "Sales Dept" and "Marketing Dept" into "Revenue Team"
2. Admin creates new team "Revenue Team"
3. Admin adds all members from both old teams to "Revenue Team"
4. Admin shares all agents from both teams with "Revenue Team"
5. Admin archives old teams (retains history but marks inactive)
6. Users see all agents they had access to previously, now under new team

### Scenario: Agent Builder Leaves Company
1. Builder who created 10 shared agents leaves org
2. Admin needs to reassign ownership of these agents
3. Admin transfers agent ownership to another builder before removing user
4. Original builder leaves, but agents continue to work
5. All replicants continue to function under new ownership
6. New owner can now push updates to agents

### Scenario: Security Incident - Credential Rotation
1. Org admin detects potential credential leak for "External API Key" (org_shared)
2. Admin immediately disables the credential
3. All agents using this credential stop working and show error
4. Admin creates new credential with rotated key
5. Admin updates all affected agents to use new credential
6. Admin re-enables agents with notification to all affected users
7. Audit trail shows who accessed old credential and when

### Scenario: Knowledge Source Versioning
1. Builder creates knowledge source "API Documentation v1"
2. Shares with "Engineering" team
3. 20 agents are built using this knowledge source
4. Builder updates documentation to "API Documentation v2" with breaking changes
5. System question: Should all agents auto-update, or should builder control rollout?
6. Option A: Create new knowledge source version, manually update agents
7. Option B: Automatic update with version pinning per agent

---

## Questions for Clarification

### Agent Sharing & Replicants

1. **Replicant Update Strategy:**
   - When builder pushes update to original agent, should replicants update immediately or on next access?
   > similar to app updates for softward: update placed in the queue, and shown in the replicant-agent ui; in the night, or when env is going into sleep state (not actively used), update rolled-out; our manually on the replicant config UI 
   - Should there be a "beta" mode where builder can test updates with select consumers first?
   > not now 
   - Can consumers temporarily "pin" their replicant to a specific version to avoid breaking changes?
   > in the options of the replicant should be 'Updates: automatic / manual' option, which is by default automatic; no special 'pin' required

2. **Forking Permissions:**
   - Can any consumer fork a replicant, or only those with specific permission?
   > only users who can build agents can fork
   - When forked, does the new agent copy all configuration including private system prompts?
   > yes, only prompts, (credentials/handover config/scheduler config) are not copied
   - Should builder have visibility into who forked their agents?
   > yes, should have a separate fork-overview list

3. **Replicant Billing:**
   - Who pays for compute/storage of replicant usage - builder's org or consumer's account?
   > each account has AI credentials in their configuration, but those are private AI credentials; once context changes to the org; AI credentials should be assigned by the org admins, each member has it's own credentials within org (to track usage on a user level) 
   - If consumer is in different org, how is billing split?
   > each account by default has it's own AI credentials, but when agent-env is build in the context of the org, it is using AI credentials assigned to that user by the org

### Credentials Management

4. **Credential Discovery:**
   - How do users discover available org_shared credentials without exposing sensitive details?
   > org shared credentials in that context only needed for the org shared agents; in this case users don't discover them themselve, they come integrated inside replicants; if user needs something separately, org will provide credentials via password manager and user would have to create credentials record himself, making it org_private
   - Should there be a credential catalog with descriptions but hidden values?
   > no, explanation given above

5. **Credential Scope:**
   - Can a credential be marked as "agent-only" (usable by agents but not directly by users)?
   > explained above; all org shared credentials are agent-only; since service doesn't have any other use for credentials, except to be provided to agents in general;
   - Can credentials have usage limits (e.g., max 100 API calls per day)?
   > not now

6. **OAuth Integration:**
   - How are OAuth credentials handled if they belong to org_private category?
   > org_private - can be created by the org, but actual setup of 'refresh/access' tokens has to be done by the user; noone from org has access to these credential's internals (values); it helps only to specify what has to be created for what agents, but credentials 'actual setup' should be completed by the user  
   - What happens when OAuth token expires - does user need to re-authorize or can admin refresh?
   > oauth credentials always comes with server-side usage, meaning refresh token; before message is sent to an agent-env, expiration of access-token needs to be checked, and if its expired, then `refresh` > `sync to agent env` > `send message`

### Organization & Team Hierarchy

7. **Team Nesting Limits:**
   - How deep can team hierarchy go (e.g., max 3 levels)?
   > max 2 levels (first level team > one level of subteams)
   - Do permissions always cascade down, or can they be restricted?
   > always cascade down

8. **Cross-Org Collaboration:**
   - Can users from different orgs collaborate on shared agents?
   > no, to collaborate on a single agent users have to be in the same org, org of the agent
   - If yes, how does permission model work across org boundaries?
   > no
   - Can agents be shared with external users (not part of any org)?
   > no

9. **Workspace vs Team Clarity:**
   - If workspaces are just for UI organization, can a workspace contain agents from multiple teams?
   > yes, in the org we could create 'expense manager agent' and 'reconciliation agent', both would be in the workspace 'Finance', but one for the 'Accounting team' and another for 'Sales Team'
   - Can workspace membership be different from team membership?
   > workspace doesn't have membership, when org builds an agent, it can assign org's workspace for it (put it in a 'folder'), when user receives access to this agent, he can find it in that workspace in his UI
   - Should there be a way to share entire workspace with a team?
   > no, workspaces are no for sharing, only for structuring

### Permissions & RBAC

10. **Permission Conflicts:**
    - User has "delete_agent" permission from Team A but Team B explicitly denies it - what wins?
    > there is no 'deny deletion' in RBAC, only 'missing or existing permission ', so situation that team A doesn't have permission and team B has it, then user has it too (as team B member) 
    - Current doc says "most permissive wins" - should there be explicit deny rules?
    > no deny rules

11. **Resource-Level Permissions:**
    - Can individual agents have their own permission overrides beyond team shares?
    > no
    - Example: Agent shared with "Sales Dept" but specific user blocked from access?
    > no

12. **Audit & Compliance:**
    - What level of audit logging is required for compliance (SOC2, GDPR)?
    > GDPR, but for now we skip this, we're in the development phase
    - Should there be immutable audit logs for all permission changes?
    > not now
    - Can org admin see all user activity or are there privacy boundaries?
    > sessions of conversations belong to the user, admins cannot see other user's sessions

### Data Ownership & Transfer

13. **Entity Ownership:**
    - When user creates agent in org context, can they take it with them if they leave?
    > no
    - Can user "donate" their private agent to org?
    > no
    - What happens to co-created resources (e.g., agent built by 2 users)?
    > in context of org - doesn't matter, agent is owned by the org in this case

14. **Bulk Operations:**
    - Can admin bulk-transfer all agents from one user to another?
    > no
    - Can admin bulk-reassign all resources from deleted team to new team?
    > no, teams are only giving access, not 'assigning' anything

15. **Data Portability:**
    - Can users export their data (agents, sessions, files) when leaving org?
    > no
    - What format should export be in (JSON, custom format)?
    > skip
    - Are there restrictions on what can be exported (e.g., org_shared credentials excluded)?
    > skip

### Knowledge Sources

read of knowledge sources here to understand them better drafts/agent_solutions_knowledge_management.md

16. **Knowledge Source Types:**
    - Are all knowledge source types handled the same way for sharing?
    > yes
    - Can database connection knowledge sources be org_private (user's credentials) or only org_shared?
    > knowledge source is not credentials; it's just access to certain articles in the DB; not relevant question

17. **Knowledge Source Updates:**
    - When knowledge source is updated, do all agents re-index immediately?
    > not relevant question
    - Is there a notification to agent owners that knowledge source changed?
    > no
    - Can agents subscribe to knowledge source update events?
    > no

### Multi-tenancy & Isolation

18. **Workspace Isolation:**
    - Are workspaces just UI constructs or do they provide data isolation?
    > we had data isolation for knowledge sources, but we'll remove it; workspaces are only UI isolation
    - Can agents in different workspaces interact with each other?
    > yes
    - Should there be workspace-level permissions in addition to team-level?
    > no

19. **Browser Context:**
    - Document mentions "browser window" for workspace selection - what about mobile apps?
    > in mobile app interface only a single workspace would be active at a time (only one browser window)
    - What about API access - how is context determined for API calls?
    > in the API we have to provide active workspace and active org to; for workspaces we already have, for orgs would be needed to add
    - Should there be a way to "lock" context to prevent accidental switching?
    > no

### Edge Cases

20. **Last Owner Problem:**
    - If last owner wants to leave, must they promote someone else first or can org be auto-deleted?
    > they have to delete org or promote someone else
    - Can system automatically promote longest-serving admin to owner?
    > no

21. **Circular Dependencies:**
    - Can Team A be parent of Team B which has permissions that Team A needs?
    > yes
    - How are circular permission dependencies resolved?
    > highest permission wins; since there is no deny, only 'allow' rules, if something is allowed from at least one 'team' or users 'role' - then it is allowed 

22. **Rate Limiting & Quotas:**
    - Are there per-user, per-team, or per-org rate limits on agent usage?
    > not yet
    - How are quotas enforced in shared replicant scenario?
    > skip
    - Does builder or consumer's quota apply?
    > skip

23. **Soft Delete vs Hard Delete:**
    - Which entities support soft delete (recoverable) vs hard delete (permanent)?
    > for now, all hard delete, soft delete will be introduced later
    - What is retention period for soft-deleted entities?
    > skip
    - Can users permanently delete immediately or must wait retention period?
    > skip

---

## Implementation Notes

### Priority 1 (Core Functionality - Must Have):
- Replicant lifecycle with automatic/manual update mechanism
- Replicant update queue with night-time/sleep-state rollout
- Basic RBAC with built-in roles (no deny rules, only allow)
- Org and team management (max 2-level nesting)
- Private vs org_private vs org_shared credentials
- OAuth credential refresh mechanism (automatic before message send)
- AI credentials per user for billing/usage tracking (private and org-assigned)
- Hard delete for all entities (no soft delete initially)
- Privacy boundaries (admins cannot see user sessions)
- Agent forking (builder permission required, prompts copied, credentials excluded)
- Fork-overview list for builders

### Priority 2 (Enhanced Features):
- Custom roles and permissions (beyond built-in roles)
- Credential rotation automation
- Credential expiration tracking and notifications
- Knowledge source management and sharing
- Workspace UI improvements (mobile app single-workspace mode)
- API context parameters (active workspace + active org)

### Priority 3 (Future Enhancements):
- Soft delete with retention periods
- GDPR audit logging
- Usage limits and quotas per user/team/org
- Beta mode for agent updates
- Version pinning for replicants
- Credential usage limits (e.g., API call quotas)
- Data export and portability

### Explicitly Not Implemented (Current Decisions):
- ❌ Cross-org collaboration (agents stay within org boundaries)
- ❌ External user sharing (must be org member)
- ❌ Deny rules in RBAC (only allow rules)
- ❌ Resource-level permission overrides (no per-agent user blocking)
- ❌ Workspace-level permissions (workspaces are UI-only)
- ❌ Workspace sharing (sharing at resource level only)
- ❌ Data export when leaving org
- ❌ User taking agents when leaving org
- ❌ Donating private agents to org
- ❌ Bulk operations (transfer agents, reassign resources)
- ❌ Automatic owner promotion
- ❌ Credential catalog/discovery UI
- ❌ Knowledge source update notifications
- ❌ Soft delete in initial implementation

### Key Design Decisions:

**Update Strategy:**
- Queue-based updates with UI notification
- Automatic rollout during off-hours or manual trigger
- Per-replicant automatic/manual setting

**Billing Model:**
- User-level AI credential tracking
- Private mode: user's private credentials
- Org mode: org-assigned credentials per user
- Enables usage tracking at individual user level

**Permission Model:**
- Allow-only rules (no explicit deny)
- Union of all team permissions + direct role
- Most permissive wins
- Max 2-level team nesting with cascading permissions

**Data Ownership:**
- Org context: org owns agents, users cannot export
- Private context: user owns data
- Hard delete only (initially)
- No grace periods or recovery

**Privacy:**
- User sessions always private (even from org admins)
- OAuth credential values never visible to org admins
- Org_shared credentials integrated into agents (no user discovery)

