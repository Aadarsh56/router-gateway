from validator import is_valid_age

def create_profile(name, age):
    if is_valid_age(age):
        return {"name": name, "age": age}
    return None
