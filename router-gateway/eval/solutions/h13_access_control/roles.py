ADMIN_IDS = {1, 2, 3}

def get_role(user_id):
    return "admin" if user_id in ADMIN_IDS else "user"
