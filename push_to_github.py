"""
GitHub Push Utility for kaviyarasukav/ads
=========================================
Pushes local repository commits directly to https://github.com/kaviyarasukav/ads.git
"""

import sys
import os
import dulwich.porcelain as dp
from dulwich.repo import Repo

def push_repo(token=None):
    repo = Repo(".")
    remote_url = "https://github.com/kaviyarasukav/ads.git"
    
    # 1. Stage and commit any outstanding changes
    status = dp.status(repo)
    if status.unstaged or status.untracked:
        print("Staging modified and untracked files...")
        dp.add(repo)
        try:
            author = b"kaviyarasukav <kaviyarasukav@users.noreply.github.com>"
            sha = dp.commit(repo, message=b"Update quant terminal, mobile UI, and download hub", author=author, committer=author)
            print(f"Created commit: {sha.decode() if isinstance(sha, bytes) else sha}")
        except Exception as e:
            print("Commit info:", e)
    
    # 2. Push with authentication
    if token:
        # Format token URL
        auth_url = f"https://{token}@github.com/kaviyarasukav/ads.git"
        print(f"Authenticating and pushing to https://github.com/kaviyarasukav/ads.git ...")
        
        success = False
        for ref in [["refs/heads/main:refs/heads/main"], ["refs/heads/master:refs/heads/main"], ["refs/heads/master:refs/heads/master"]]:
            try:
                dp.push(repo, auth_url, refspecs=ref)
                print(f"SUCCESS: Pushed {ref[0]} to https://github.com/kaviyarasukav/ads.git!")
                success = True
                break
            except Exception as ex:
                continue
                
        if not success:
            # Try default push
            try:
                dp.push(repo, auth_url)
                print("SUCCESS: Pushed to https://github.com/kaviyarasukav/ads.git!")
                success = True
            except Exception as e:
                print("Push failed with error:", e)
                print("Tip: Ensure your GitHub Token has 'repo' (read & write) permissions.")
    else:
        print("\n[!] No GitHub Token provided.")
        print("To push automatically, please provide your GitHub Personal Access Token (PAT):")
        print("  python push_to_github.py <YOUR_GITHUB_TOKEN>\n")

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    push_repo(t)

