from roles import get_role

def can_delete(user_id):
    role = get_role(user_id)
    if role == "admin":
        return False
    return True

def can_view(user_id):
    return True
