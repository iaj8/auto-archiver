import json

# Load the cookies from the JSON file
with open('../../../secrets/json_cookies.txt', 'r') as f:
    cookies = json.load(f)

# Convert cookies to Netscape format
netscape_cookies = []
for cookie in cookies:
    domain = cookie.get('domain', '')
    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
    path = cookie.get('path', '/')
    secure = 'TRUE' if cookie.get('secure') else 'FALSE'
    expiration = cookie.get('expirationDate', 0)
    name = cookie.get('name', '')
    value = cookie.get('value', '')
    netscape_cookies.append(f"{domain}\t{flag}\t{path}\t{secure}\t{int(expiration)}\t{name}\t{value}")

# Save the Netscape formatted cookies to a new file
with open('../../../secrets/netscape_cookies.txt', 'w') as f:
    f.write("# Netscape HTTP Cookie File\n")
    for line in netscape_cookies:
        f.write(line + "\n")
