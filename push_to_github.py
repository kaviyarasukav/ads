"""
GitHub Push Utility for kaviyarasukav/ads
=========================================
"""

import sys
import os
import dulwich.porcelain as dp
from dulwich.repo import Repo

def push(token=None):
    repo = Repo(".")
    remote_url = "https://github.com/kaviyarasukav/ads.git"
    
    if token:
        # Inject token into URL for authenticated HTTPS push
        auth_url = f"https://{token}@github.com/kaviyarasukav/ads.git"
        print(f"Pushing to {remote_url} using provided authentication token...")
        try:
            dp.push(repo, auth_url, refspecs=["refs/heads/main:refs/heads/main"])
            print("Successfully pushed branch 'main' to https://github.com/kaviyarasukav/ads!")
        except Exception as e:
            try:
                # Try master if main fails
                dp.push(repo, auth_url, refspecs=["refs/heads/master:refs/heads/main"])
                print("Successfully pushed branch 'master' to 'main' on https://github.com/kaviyarasukav/ads!")
            except Exception as e2:
                print("Push error:", e2)
    else:
        print("No GitHub token provided. To push, run:")
        print("python push_to_github.py <YOUR_GITHUB_PERSONAL_ACCESS_TOKEN>")

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_TOKEN")
    push(t)
