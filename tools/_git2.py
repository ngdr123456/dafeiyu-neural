import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\Users\22082\Desktop\DEPSK\books\ego-dialogue"
OLD = r"C:\Users\22082\Desktop\DEPSK\_backup\ego-dialogue_20261030_222557"
CUR = r"C:\Users\22082\Desktop\DEPSK\_backup\ego-dialogue_20261031_084123"
os.chdir(ROOT)

# ① 删掉只含 3 个提交的历史，从头建（只有 2 个提交，成本很低）
shutil.rmtree(os.path.join(ROOT, ".git"), ignore_errors=True)
subprocess.run(["git", "init", "-q"], cwd=ROOT, check=False)
for k, v in (("user.email", "local@localhost"), ("user.name", "local"),
             ("core.autocrlf", "false"), ("core.quotepath", "false")):
    subprocess.run(["git", "config", k, v], cwd=ROOT, check=False)
print("  .git 已重建（清掉那次被污染的提交）")

# ② 先 add 一次拿到跟踪清单
subprocess.run(["git", "add", "-A"], cwd=ROOT, capture_output=True)
out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True)
files = [x for x in out.stdout.decode("utf-8", "replace").splitlines() if x.strip()]
print("  跟踪 %d 个文件" % len(files))


def restore(base, label):
    n, miss = 0, 0
    for f in files:
        src = os.path.join(base, f.replace("/", os.sep))
        dst = os.path.join(ROOT, f.replace("/", os.sep))
        if not os.path.exists(src):
            miss += 1
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    print("  %s：恢复 %d｜缺 %d" % (label, n, miss))


restore(OLD, "① 还原旧快照")
subprocess.run(["git", "add", "-A"], cwd=ROOT, capture_output=True)
subprocess.run(["git", "commit", "-q", "-m",
                "baseline: 2026-10-30 22:25 快照（20261030 晚间三批之前）"], cwd=ROOT, check=False)

restore(CUR, "② 恢复当前")
subprocess.run(["git", "add", "-A"], cwd=ROOT, capture_output=True)
subprocess.run(["git", "commit", "-q", "-m",
                "本批之后：先接住 + idle 冷却 + 校验误报 + run_id"], cwd=ROOT, check=False)

log = subprocess.run(["git", "log", "--oneline"], cwd=ROOT, capture_output=True)
print()
print("  提交历史（应为 2 条）：")
for ln in log.stdout.decode("utf-8", "replace").splitlines():
    print("     %s" % ln)
