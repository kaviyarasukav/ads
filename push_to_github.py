"""
GitHub Push Utility for kaviyarasukav/ads
=========================================
Pushes local repository commits directly to https://github.com/kaviyarasukav/ads.git
"""

import sys
import os
import subprocess
import dulwich.porcelain as dp
from dulwich.repo import Repo

def push_repo(token=None):
    # Try Git CLI first if available
    git_cmd = r"C:\Users\23aiml29\mingit\cmd\git.exe"
    if not os.path.exists(git_cmd):
        git_cmd = "git"

    if token:
        auth_url = f"https://{token}@github.com/kaviyarasukav/ads.git"
        print(f"Pushing branches to https://github.com/kaviyarasukav/ads.git via Git CLI...")
        for branch in ["master", "main"]:
            res = subprocess.run([git_cmd, "push", auth_url, branch], capture_output=True, text=True)
            if res.returncode == 0:
                print(f"SUCCESS: Pushed {branch} to GitHub!")
            else:
                print(f"Git CLI push for {branch} returned code {res.returncode}: {res.stderr.strip() or res.stdout.strip()}")
                # Fallback to dulwich
                try:
                    repo = Repo(".")
                    dp.push(repo, auth_url, refspecs=[f"refs/heads/{branch}:refs/heads/{branch}".encode()])
                    print(f"SUCCESS (Dulwich): Pushed {branch} to GitHub!")
                except Exception as e:
                    print(f"Dulwich push failed for {branch}: {e}")
    else:
        print("\n[!] No GitHub Personal Access Token provided.")
        print("To push automatically, run:")
        print("  python push_to_github.py <YOUR_GITHUB_TOKEN>")
        print("Or set the environment variable:")
        print("  $env:GITHUB_TOKEN = '<YOUR_GITHUB_TOKEN>'; python push_to_github.py\n")

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    push_repo(t)
