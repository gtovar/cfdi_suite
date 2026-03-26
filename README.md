<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/ca872c8e-ab8b-48b7-9548-205f28aeea7a

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Run the app:
   `npm run dev`

## AI Workflow

This repo keeps AI task control in versioned docs:

- Workflow: [`docs/ai/workflow.md`](docs/ai/workflow.md)
- Policy: [`docs/ai/implementation-policy.md`](docs/ai/implementation-policy.md)
- Templates: [`docs/ai/templates/`](docs/ai/templates/)
- UI testing baseline: [`docs/ai/ui-testing-baseline.md`](docs/ai/ui-testing-baseline.md)

Before implementation work, classify the task as `exploration`, `implementation`, or `hotfix` and use the corresponding template.
