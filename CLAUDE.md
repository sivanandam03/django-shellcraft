# django-shellcraft

## What is this?
A Django package that brings Rails-style console ergonomics to the Django shell.
Targets developers migrating from Ruby on Rails to Django who miss the
`rails console` experience — specifically `awesome_print` style output,
model shortcuts, and schema inspection.

## Package identity
- PyPI name: `django-shellcraft`
- Importable name: `shellcraft`
- INSTALLED_APPS entry: `'shellcraft'`
- Management command: `python manage.py shellcraft`
- Author: Siva
- Python: 3.8+
- Django: 3.2, 4.0, 4.1, 4.2, 5.0

## Dependencies
- django >= 3.2
- django-extensions >= 3.0 (handles model auto-loading, we build on top)

## Project structure
django-shellcraft/
├── shellcraft/
│   ├── __init__.py                        # version only
│   ├── printer.py                         # awesome_print style renderer
│   ├── mixins.py                          # Rails-style shortcuts injected on models
│   └── management/
│       └── commands/
│           └── shellcraft.py              # manage.py shellcraft command
├── tests/
│   └── test_printer.py
├── pyproject.toml
├── README.md
└── LICENSE

## Core features to build
1. `User.find(1)`              → User.objects.get(pk=1)
2. `User.all()`                → User.objects.all()  — pretty printed
3. `User.where(active=True)`   → User.objects.filter() — pretty printed
4. `User.first()`              → User.objects.first()
5. `User.last()`               → User.objects.last()
6. `User.count()`              → User.objects.count()
7. `user.update(email="x")`    → instance-level update + save
8. `user.destroy()`            → user.delete() alias
9. `User.fields()`             → schema inspection, colored output
10. `tables()`                 → list all models across all apps

## printer.py — awesome_print style rules
Color mapping (ANSI, pure Python — zero dependencies):
- int, float     → blue
- str            → yellow
- True           → green
- False          → red
- None           → red
- datetime, date → cyan
- field types    → cyan
- index [0],[1]  → gray

Single record output:
#<User:0x001> {
    :id         => 1,
    :username   => "siva",
    :is_active  => true,
}

Multiple records output:
[
    [0] #<User:0x001> {
            :id       => 1,
            :username => "siva",
        },
    [1] #<User:0x002> {
            :id       => 2,
            :username => "kumar",
        }
]
2 records

## mixins.py — design decisions
- Inject methods onto Django base Model class at shell startup only
- Guard: only activate when running manage.py shellcraft
- Collision check: warn if injected method name clashes with existing model method
- Never activate in production — raise SystemExit if DEBUG is False

## Key design decision
Do NOT patch __repr__ globally. Pretty printing only happens through
our helper methods (User.all(), User.find() etc). Raw User.objects.all()
still shows Django default output. Intentional — predictable over magic.

## Current status
- [x] pyproject.toml
- [x] shellcraft/__init__.py
- [ ] shellcraft/printer.py
- [ ] shellcraft/mixins.py
- [ ] shellcraft/management/commands/shellcraft.py
- [ ] tests/test_printer.py
- [ ] README.md
- [ ] LICENSE

## Start here
Begin with printer.py — everything else depends on it.
Once colors and formatting work, mixins.py becomes straightforward.