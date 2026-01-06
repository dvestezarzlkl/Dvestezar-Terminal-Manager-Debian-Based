# Tokens for Private Plugins

This directory contains access tokens for private plugins.

Files:

- `<plugin_id>.cd`

Each file contains exactly one line:

`<username>:<token>`

Never commit tokens.

## Token files MUST

- be named `<plugin_id>.cd`, where `<plugin_id>` matches the plugin identifier in `plugins.jsonc`, and must end with `.cd`
- contain exactly one line in the format `<username>:<token>`
- never be committed to Git

Only `*.cd` files are treated as access tokens.  
These files are ignored by Git via `.gitignore`.

## Token files MUST NOT

- contain extra spaces, new lines, or any other characters
- be committed to Git repositories
- be shared publicly
- be stored in any other format
- be named differently than `<plugin_id>.cd`
- be empty
- contain multiple lines
- contain comments
- be stored in any other directory
- be used for any other purpose
