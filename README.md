# Overview

This project implements a zero-cost automation pipeline that converts service business call transcripts into Retell AI voice agent configurations.

The system processes:

Demo calls → Preliminary Agent (v1)

Onboarding calls/forms → Updated Agent (v2)

The pipeline simulates Clara’s real onboarding workflow:

Human conversation → structured operational rules → AI voice agent configuration.

The solution is designed to be:

* Zero-cost

* Repeatable

* Batch-capable

* Idempotent

* Versioned

Automation orchestration is handled using n8n, while Python scripts generate account memos and agent specifications.

# Retell Agent Draft Spec

Each generated agent_spec.json contains:

* agent_name

* voice_style

* system_prompt

* key_variables

* call_transfer_protocol

* fallback_protocol

* version

* The system prompt includes:

* Business hours flow

* After-hours call handling

* Emergency detection

* Transfer routing

* Transfer fallback logic

# Manual Import into Retell UI

Steps:

1. Log in to Retell AI Dashboard

2. Create a New Voice Agent

3. Open:

  outputs/accounts/<account_id>/v2/agent_spec.json

4. Copy the following values into the Retell UI:
```
* Retell Field -	Source
* Agent Name -	agent_name
* Prompt	- system_prompt
* Voice Style -	voice_style
* Variables -	key_variables
```
5. Configure call transfer logic using:

call_transfer_protocol

6. Configure fallback messaging using:

fallback_protocol

This recreates the generated Clara voice agent.

# n8n Setup

n8n is used to orchestrate the automation pipeline.

* Start n8n with Docker
docker compose up

n8n will be available at:
http://localhost:5678
Environment Variables

The system does not require paid APIs.
Optional environment variables:
N8N_ENABLE_COMMANDS=true

# Import the n8n Workflow

* Open n8n

* Navigate to Workflows → Import
Import:
workflows/n8n_workflow.json

# To process the entire dataset:

Open the workflow in n8n

Click Execute Workflow
