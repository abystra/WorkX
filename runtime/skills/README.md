# Curated Skills

Agent SDK plugins reviewed for use by WorkX workmates (Part 4 §6, "plugins" and "skills"). Each Skill lives
in its own directory with a `workx-skill.yaml` manifest (id, version, review record, required tools) and is
copied into the E2B template at `/mnt/skills`. The ids match the catalog in
`services/workx/src/workx/domains/agents/catalog.py`.

No Skill content is committed yet: the catalog entries (slides, deep-research, data-visualization,
product-prototype, office, image) are placeholders until each Skill passes review. The runtime already
passes the allowed Skill ids to the SDK (`skills=[...]`) and the plugin paths from the RunSpec.
