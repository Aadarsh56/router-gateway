from email_utils import get_domain
def test_basic():     assert get_domain("user@example.com")     == "example.com"
def test_subdomain(): assert get_domain("me@mail.company.org")  == "mail.company.org"
def test_different(): assert get_domain("admin@test.io")         == "test.io"
