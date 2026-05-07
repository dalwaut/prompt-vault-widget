# Prompt Vault Desktop Widget

A lightweight Linux desktop widget for saving, tagging, and reusing AI prompt snippets. Click any prompt to copy it to your clipboard.

## Features

- **Save prompts** — Click + to add a named prompt with tags
- **Click to copy** — Click any prompt to paste it to clipboard instantly
- **Tag system** — Organize prompts with comma-separated tags
- **Paste from clipboard** — Quick-paste your current clipboard into a new prompt
- **Prompt preview** — See first 40 chars of each prompt in the list
- **Delete on hover** — X button appears when hovering a prompt
- **Scrollable** — Scroll wheel for large collections
- **Draggable** — Click and drag the title bar
- **Adjustable transparency** — Opacity slider in settings
- **Auto Start** — Toggle to launch on login
- **Emerald green theme** — distinct from other BB widgets
- **Purely local** — JSON storage, no cloud, no tracking

## Requirements

```bash
sudo apt install python3-gi python3-gi-cairo
```

## Install

```bash
git clone https://github.com/dalwaut/prompt-vault-widget.git
cd prompt-vault-widget
chmod +x prompt-vault-widget.py
./prompt-vault-widget.py
```

Or install via [BB Widget Manager](https://github.com/dalwaut/bb-widgets).

## Built by [Boutabyte](https://boutabyte.com)

## License

MIT
