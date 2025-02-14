import re
import hashlib

def make_features(input_str, length=3):
    """Break the input string into features (shingles) of given length."""
    input_str = input_str.lower()
    out_str = re.sub(r'[^\w]+', '', input_str)
    return [out_str[i:i + length] for i in range(max(len(out_str) - length + 1, 1))]


def hash_feature(feature):
    """Hash a feature using a simple hash function (md5)."""
    return int(hashlib.md5(feature.encode()).hexdigest(), 16) & ((1 << 64) - 1)


def make_simhash(input_str, hash_size=64):
    """Compute the SimHash value for the input string."""
    features = make_features(input_str)
    v = [0] * hash_size

    for feature in features:
        hash_value = hash_feature(feature)
        for i in range(hash_size):
            bit = (hash_value >> i) & 1
            v[i] += 1 if bit else -1

    # Convert the vector into a SimHash
    simhash = 0
    for i in range(hash_size):
        if v[i] > 0:
            simhash |= (1 << i)
    return simhash


def simhash_diff(hash_1, hash_2):
    """Calculate the difference between two SimHash values."""
    x = hash_1 ^ hash_2
    return bin(x).count('1')
