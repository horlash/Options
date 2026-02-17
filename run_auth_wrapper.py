
import sys
import os
# Mock print to capture the URL
original_print = print
def captured_print(*args, **kwargs):
    msg = " ".join(map(str, args))
    original_print(msg)
    if "https://partner.schwab.com" in msg:
        with open("auth_url.txt", "w") as f:
            f.write(msg)

# Monkey patch print? No, that's messy.
# The library uses print(). 
# Let's just run it and manually capture stdout to a file inside the python process
# actually 'client_from_manual_flow' handles the printing.

# Better approach: 
# The library prints "Open this URL to authenticate: <URL>"
# I can just run the script and let it print to metadata file?

# Let's just modify the auth script to redirect stdout to a file at python level
if __name__ == "__main__":
    sys.stdout = open("auth_stdout.txt", "w", encoding='utf-8')
    sys.stderr = sys.stdout
    
    try:
        import schwab_auth
        schwab_auth.authenticate()
    except Exception as e:
        print(e)
    finally:
        sys.stdout.close()
