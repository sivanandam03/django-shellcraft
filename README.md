# django-shellcraft

Rails-style console ergonomics for Django — pretty printing, model shortcuts, and schema inspection.

Built for developers migrating from Ruby on Rails who miss the `rails console` experience.

---

## Installation

```bash
pip install django-shellcraft
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "shellcraft",
]
```

## Usage

```bash
python manage.py shellcraft
```

All models are auto-imported into the shell namespace. IPython is used when available, falling back to the standard Python REPL.

> **Note:** shellcraft refuses to start when `DEBUG = False` as a production safety guard.

---

## Features

### Model shortcuts

All shortcuts are injected as classmethods/instance methods at shell startup. Raw `User.objects.all()` is unchanged — pretty printing only happens through shellcraft methods.

| Method | Equivalent |
|---|---|
| `User.find(1)` | `User.objects.get(pk=1)` |
| `User.all()` | `User.objects.all()` + pretty print |
| `User.where(is_active=True)` | `User.objects.filter(...)` + pretty print |
| `User.first()` | `User.objects.first()` + pretty print |
| `User.last()` | `User.objects.last()` + pretty print |
| `User.count()` | `User.objects.count()` |
| `user.update(email="x@y.com")` | sets attrs + `save()` |
| `user.destroy()` | `user.delete()` |
| `User.fields()` | colored schema inspection |
| `tables()` | list all models across all apps |

### Pretty printing

Single record:

```
#<User:0x7f3a> {
    :id         => 1,
    :username   => "alice",
    :email      => "alice@example.com",
    :is_active  => true,
    :created_at => 2024-01-15 10:30:00,
}
```

Multiple records:

```
[
    [0] #<User:0x7f3a> {
            :id       => 1,
            :username => "alice",
        },
    [1] #<User:0x7f3b> {
            :id       => 2,
            :username => "bob",
        }
]
2 records
```

Color mapping:

| Type | Color |
|---|---|
| `int`, `float` | blue |
| `str` | yellow |
| `True` | green |
| `False`, `None` | red |
| `datetime`, `date` | cyan |
| field types | cyan |
| record index `[0]` | gray |

### Schema inspection

```python
User.fields()
```

```
User {
    :id          AutoField
    :username    CharField
    :email       CharField
    :is_active   BooleanField
    :created_at  DateTimeField
    :group_id    ForeignKey     null: true
}
```

### List all tables

```python
tables()
```

```
  auth.User
  auth.Group
  auth.Permission
  myapp.Post
  myapp.Comment

5 tables
```

### Manual pretty printing

`ap()` is available directly for any model instance or queryset:

```python
ap(User.objects.filter(is_staff=True))
```

---

## Requirements

- Python 3.8+
- Django 3.2, 4.0, 4.1, 4.2, or 5.0
- django-extensions >= 3.0

Optional: `ipython` for an enhanced shell experience.

---

## Development

```bash
git clone https://github.com/sivanandam03/django-shellcraft
cd django-shellcraft
pip install -e ".[dev]"
pytest
```

---

## License

MIT
