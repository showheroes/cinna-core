# Management of Organisations / Teams / Users

Reference to business logic for agent sessions: docs/agent-sessions/business_logic.md

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

#### Credentials 'org_shared'

They are managed centrally by org admins and can be used (read) by singular users (teams) they are shared with,
but these credentials can only be modified by users who have such permission.

### Knowledge Source Sharing

Knowledge sources are shared as regular entities: either to a user directly or to a team.
They can be private or org managed.
Once user is having access to read certain knowledge source, this knowledge source becomes available to all of his agents.

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

### Organisations

Organisations - top level to group teams and users together. 

Details:
- User could belong to an organisation or can be in a 'private mode'.
- User can switch between 'Org mode' and 'private mode'.
- Meaning user's account by default is private, but he can create new or join to other organisations.
- Switching between different orgs or private mode - matter of the current browser window (not permanent). 
- Meaning user can have 2 browser windows opened, one for some org and one for private mode.
- Active org (or private mode), similar to the behavior of workspaces, defines what  

User stories:
- User creates his account
- User creates Org and becomes org owner
- User goes into the list of Org members, clicks to "Invite user" and inserts username of another user
- If user is found, invitation is created
- If user accepts invitation - he joins the org; if rejects - invitation marked as rejected
- In the invitation org admin can specify in advance: what teams this user should granted once joined, what role this user should get in the org

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
  - view_all
  - org_wide_share
  - org_wide_unshare
  - ...
- team
  - create
  - view
  - delete
  - ...
etc.

Meaning we have default built-in RBAC, and it is applied on org creation, but user can improve that to his needs.

### Workspaces

Workspaces - is a way to organize data and reduce UI clutter.

Details:
- They can be treated as "Folders" for the entities like "Agents", "Credentials", "Sessions", etc.
- They are not used to manage permissions, only to manage visibility of certain entities in the UI.
- To manage group access should be used Teams instead of Workspaces.
- Workspace can be managed by the user, if he created that in a "private" mode, or "Workspace" could become "Org Workspace", managed by Org Admins.
- When user switches between context (private / selected org), workspaces for selection are loaded according to the context.
- Within context of an org, user can still create private workspaces visible only to him, and create inside those private entities (agents, credentials, etc.)
- User cannot manage org workspaces unless he has permission to do so, given by the org admin.
- Workspaces always browser window related, meaning 2 browser windows can be in different workspaces for the same user.
- Although, visibility of the workspace is considered by the current active org.
- For example: User has private workspaces like 'Home Agents', 'Pet-Project Agents', etc.; while in the context of org he is a member of he has workspaces like 'Office Agents', 'Infrastructure Agents'. 


### Teams

Teams - always belong to an organisation, it's an org sub-unit that primarily exists for permissions management.
Teams is basically a way to assign certain role to a user through a group.
Since users can be in multiple teams, RBAC permissions check made across all teams and roles assigned to these teams. 

User story:
- User can create a team named "Sales Dept".
- User built a new agent, like "CRM Assistant"
- User gives permission: Users from "Sales Dept" can have access to the "CRM Assistant" agent as "Regular" users (role).
- Now users from that team can use that agent as "Regular" users.


