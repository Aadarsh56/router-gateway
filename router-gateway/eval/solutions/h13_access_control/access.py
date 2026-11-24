from roles import get_role

def can_delete(user_id):
    role = get_role(user_id)
    if role == "admin":
        return True
    return False

def can_view(user_id):
    return True
