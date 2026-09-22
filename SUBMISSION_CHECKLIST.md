# FE Bar submission checklist

Status of everything the submission form asks for. **Nothing has been submitted** - this is prep.

## Ready in this repo
- [x] **The build** - 6 connected layers assembled under `01_`…`06_`, one governed schema.
- [x] **Execution evidence as text** - `evidence/RUN_EVIDENCE.md` (live output: row counts,
      6+14 constraints, certified-metric results, cross-domain join, dollar exposure, Genie
      NL→SQL→answer trace). *This is the #1 pass-blocker and it's covered.*
- [x] **Integrated narrative** - `README.md` leads with business outcome, shows the connected
      data flow, and maps every layer.
- [x] **Six form answers drafted** - `SUBMISSION.md` (customer, vertical, challenge, solution,
      AI tools & trade-offs, outcomes).
- [x] **Decisions & trade-offs** - `docs/DECISIONS_AND_TRADEOFFS.md`.
- [x] **Presentation deck** - `deck/DECK.md` (outcome-led; exec + technical framing), also
      built as a Databricks-themed Google Slides deck (11 slides):
      https://docs.google.com/presentation/d/1UwpZ4cDG45zzxq8bEWLoRybua6tigIsQ_K75isReq3s/edit
- [x] **Synthetic data only** - no real customer data; anonymized customer name.

## You must do (form actions - I won't submit for you)
- [ ] **Push the repo** to `ritwikamukherjee/fe-bar-medicare-appeals-agent` (private).
- [ ] **GitHub repo link** - paste the repo URL. Since it's private, either make it public or
      use the form's "connect GitHub" so the validator can read it. *(Scoring is from the
      local folder you select, so this link is for reviewer reference.)*
- [ ] **Attach the deck file** - attach `deck/DECK.md` (or export it to PDF and attach that).
- [ ] **Select the local repo folder** - point the form's "Choose repo folder" at
      `~/claude-code/fe-bar-medicare-appeals-agent`.
- [ ] **Paste the six answers** from `SUBMISSION.md` into the matching fields.
- [ ] **Conversation ID (optional)** - this build session's ID (run `/status`, or the newest
      `~/.claude/projects/<project>/*.jsonl` filename).
- [ ] **Attestation** - check the box and type your full name. Do **not** check the "AI
      Customer Challenge" box (that's for the 8 fictional scenarios + a trained/served ML
      model; this is a real-customer Gen AI build).
- [ ] **AI role-play (Yoodli)** - set aside for now, per your call.

## Optional strengthening before submitting
- [ ] Add per-member/per-claim UC-function output to `evidence/` (agent tool proof).
- [ ] Export the deck to PDF for a cleaner business artifact.
- [ ] Add the overturn-likelihood ML model (roadmap item) if you want an ML + Gen AI story.
