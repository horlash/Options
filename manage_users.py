import json
import os
import hashlib
import sys
import getpass

USERS_FILE = os.path.join(os.path.dirname(__file__), 'backend', 'users.json')

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def add_user():
    username = input("Enter username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
        
    users = load_users()
    if username in users:
        print(f"User '{username}' already exists.")
        confirm = input("Overwrite password? (y/n): ").lower()
        if confirm != 'y':
            return
            
    password = getpass.getpass("Enter password: ")
    confirm_pass = getpass.getpass("Confirm password: ")
    
    if password != confirm_pass:
        print("Passwords do not match.")
        return
        
    users[username] = hash_password(password)
    save_users(users)
    print(f"✅ User '{username}' added/updated successfully.")

def list_users():
    users = load_users()
    if not users:
        print("No users found.")
    else:
        print("Registered Users:")
        for user in users:
            print(f"- {user}")

def remove_user():
    username = input("Enter username to remove: ").strip()
    users = load_users()
    
    if username in users:
        del users[username]
        save_users(users)
        print(f"✅ User '{username}' removed.")
    else:
        print(f"User '{username}' not found.")

def main():
    while True:
        print("\n=== User Management ===")
        print("1. Add/Update User")
        print("2. Remove User")
        print("3. List Users")
        print("4. Exit")
        
        choice = input("Select option (1-4): ")
        
        if choice == '1':
            add_user()
        elif choice == '2':
            remove_user()
        elif choice == '3':
            list_users()
        elif choice == '4':
            break
        else:
            print("Invalid option.")

if __name__ == "__main__":
    main()
