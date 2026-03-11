import os

dirs = [
    "_source/lewis_structures",
    "_source/lewis_structures/pdf",
    "_source/lewis_structures/verification"
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    print(f"Created/Verified directory: {d}")

print("\nFiles in _source:")
for f in os.listdir("_source"):
    if f.endswith(".chem"):
        print(f"  {f}")
