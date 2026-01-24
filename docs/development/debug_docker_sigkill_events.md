
In the logs of the container you'd see CLAUDE CODE errors like:
```
claude_agent_sdk._internal.query - ERROR - Fatal error in message reader: Command failed with exit code -9 (exit code: -9)
Error output: Check stderr output for details
2026-01-24 12:29:46,722 - core.server.adapters.claude_code - ERROR - Session died with SIGKILL
2026-01-24 12:29:46,722 - core.server.adapters.claude_code - ERROR - CLI stderr:
No stderr output captured
2026-01-24 12:29:46,722 - core.server.routes - INFO - [Stream event #4] Received chunk type=error, content_length=40
```


How to look for such issues in the docker daemon:
```
# Watch memory usage
docker stats [CONTAINER_ID]

# Check for more OOM events
docker events --filter 'type=container' --filter 'event=oom'

# Or to track one exact container
docker events --filter "container=[CONTAINER_ID]"
```


In case of OOM error in the events logs you'd see something like:
```
2026-01-24T13:29:46.408968750+01:00 container oom 94b74b1db5930e2318ceba9c923c4e71acef85adb45d604b4094f374ec77a6e2 (com.docker.compose.config-hash=37e7ed796aec54da945d5b720995093f6206a45b762ad757c922bc7fbd0280f6, com.docker.compose.container-number=1, com.docker.compose.depends_on=,......... 
```
