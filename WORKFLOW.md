# Workflow — saving work & deploying

A plain-English reminder of the everyday Git + deploy loop for this project.

---

## The one thing to remember

**"Saving to GitHub" is two separate steps:**

| Step | Command | What it does | Where it lives |
|------|---------|--------------|----------------|
| Save a checkpoint | `git commit` | Records a snapshot of your changes | **Your machine only** |
| Back it up | `git push` | Uploads your commits to GitHub | **GitHub (the cloud)** |

A commit by itself is **not** on GitHub yet — it's a local save point.
`push` is the step that actually sends it up.

> Rule of thumb: **commit = save, push = back up.**
> Push whenever you'd be sad to lose what you just did.

---

## Daily loop

As you work, commit small finished chunks (cheap — do it freely):

```bash
git add -A                       # stage everything you changed
git commit -m "what I just did"  # save a checkpoint (local)
```

When you pause — end of day at a minimum, but more often is safer:

```bash
git push                         # back up all your commits to GitHub
```

One `git push` sends up **all** the commits you've made since the last push.

Why push more than once a day? A push is your backup. If you only push at the
end of the day and the laptop dies at 4pm, you lose the day. Push whenever you
finish something meaningful.

---

## Checking where things stand

```bash
git status                       # what's changed but not yet committed
git log --oneline -10            # recent commits
git status -sb                   # also shows if you're "ahead" of GitHub
```

If `git status -sb` says **"ahead of 'origin/main' by N commits"**, that means
you have N commits saved locally that aren't backed up to GitHub yet → time to
`git push`.

---

## Two meanings of "deploy" — keep them separate

1. **Deploy to GitHub** = `git push`. This is your backup + history. It does
   **not** change what's running on the stream.

2. **Deploy to the stream** = restart the running services so they pick up the
   new code:
   ```bash
   docker compose restart bot overlay
   ```
   The code is mounted into the containers, so a restart is enough — no rebuild
   needed for normal code changes. These run the new code right away.

You can do one without the other. Pushing to GitHub doesn't touch the stream;
restarting the stream doesn't touch GitHub.

---

## Branches (only when you want them)

For everyday solo work, committing straight to `main` and pushing is perfectly
fine. You only need a branch when you want a throwaway space to try something
risky without disturbing `main`:

```bash
git checkout -b try-something    # start a branch off main
# ...commit your experiment...
git checkout main                # go back to main
git merge try-something          # if it worked, fold it into main
git branch -d try-something      # delete the branch (commits are safe on main)
```

If the experiment flopped, just `git checkout main` and delete the branch —
`main` was never touched.

> A **pull request** is just GitHub's web page for reviewing and merging a
> branch into `main`. Handy when someone else reviews your code; for solo work
> you can merge it yourself on your machine (as above) and skip the PR.

---

## Cheat sheet

```bash
# save + back up (the everyday loop)
git add -A && git commit -m "message" && git push

# where am I?
git status -sb
git log --oneline -10

# deploy the new code to the stream
docker compose restart bot overlay
```
