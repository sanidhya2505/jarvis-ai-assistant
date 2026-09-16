#!/bin/bash
for d in app app/config app/core app/ai app/rag app/memory app/tasks app/calendar app/scheduler app/notifications app/voice app/files app/database app/api app/ui tests; do
  touch "/home/claude/JARVIS/$d/__init__.py"
done
