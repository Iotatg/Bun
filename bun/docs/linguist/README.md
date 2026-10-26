# Bun and GitHub Linguist

GitHub does not know the language Bun yet. Linguist has no entry for the
extension `.bun`, so every file of the language is invisible to it, and
the bar of the repository shows only the two languages that it does know.

## Why the bar shows Python 87.8% and C 12.2%

The two numbers are exact, and they are not a mistake of Linguist.
Linguist counts the **bytes** of the files, not the lines:

| language | files | bytes | share |
|----------|-------|-------|-------|
| Python   | 97    | 1 063 008 | 87.5% |
| C        | 1     | 151 188   | 12.5% |
| Bun      | 58    | 372 565   | **not counted** |

- The Python files are the implementation of the language: the compiler,
  the checker, the three engines and the C backend. They are the biggest
  part of the repository, so Python is the biggest part of the bar.
- The one C file is `lib/bun/c_runtime.h`, the runtime that the C backend
  compiles against.
- The 58 Bun files are the self-hosted front end, the golden corpus and
  the examples. Linguist drops them, because it has never heard of the
  extension `.bun`.

The Markdown files of the repository do not show up either: Linguist
excludes the `docs/` directory and the `README.md` from the statistics
(`lib/linguist/documentation.yml`).

## What the bar will look like

When the entry for Bun lands in Linguist, the bar of the repository
becomes:

| language | bytes | share |
|----------|-------|-------|
| Python   | 1 063 008 | 67.0% |
| Bun      | 372 565   | 23.5% |
| C        | 151 188   | 9.5%  |

## What is in this directory

The files here are the material of the pull request that adds Bun to
Linguist. Nothing here is needed to run the language; the directory only
holds the material of the pull request.

| file | where it goes in `github-linguist/linguist` |
|------|--------------------------------------------|
| `Bun.tmLanguage.json` | `grammars/Bun.tmLanguage.json` |
| `languages.yml.snippet` | the entry inside `lib/linguist/languages.yml` |
| `samples/*.bun` | `samples/Bun/` |

## The steps of the pull request

1. Fork `github-linguist/linguist` and create a branch.
2. Copy `Bun.tmLanguage.json` into `grammars/`.
3. Copy the three files of `samples/` into `samples/Bun/`.
4. Add the entry of `languages.yml.snippet` to `lib/linguist/languages.yml`,
   in the alphabetical place of the name. The `language_id` is a number
   that the maintainers hand out, so the number of the snippet is a
   placeholder.
5. Run the tests of Linguist: `bundle exec rake test`. The test of the
   samples checks that every language of the list has samples, and that
   the grammar of the samples detects them.
6. Open the pull request.

Until the pull request lands, `.gitattributes` already names the language
for the files that carry the `linguist-language` attribute, so the
repository is ready the moment the entry is merged:

```gitattributes
*.bun linguist-language=Bun
```

Linguist ignores an attribute that names a language it does not know, so
the attribute changes nothing until the entry lands, and it costs
nothing afterwards.
