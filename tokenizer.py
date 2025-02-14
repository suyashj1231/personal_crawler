import sys
import re

Token = ""


def tokenize(text: str) -> list[Token]:
    ''' Tokenizes raw text instead of assuming a file path.
        Uses regex to extract words (a-z, A-Z, 0-9) and converts them to lowercase.
    '''
    regex_pattern = re.compile(r"[A-Za-z0-9]+")
    return [word.lower() for word in regex_pattern.findall(text)]


def compute_word_frequencies(tokens: list[Token]) -> dict[Token, int]:
    '''Uses the tokenized list and adds them to a frequency dictionary.'''
    token_dict = {}
    for i in tokens:
        token_dict[i] = token_dict.get(i, 0) + 1
    return token_dict


def print_frequencies(frequencies: dict[Token, int]) -> None:
    ''' Prints sorted tokens in the format "word -> frequency". '''
    sorted_dict = sorted(frequencies.items(), key=lambda item: item[1], reverse=True)
    for i, j in sorted_dict:
        print(f"{i} -> {j}")


def main():
    ''' Modifies function to accept raw text input instead of a file path. '''
    if len(sys.argv) != 2:
        print("Error: Wrong Argument")
        sys.exit(1)

    text = sys.argv[1]  # Accept raw text
    tokens = tokenize(text)
    token_dict = compute_word_frequencies(tokens)
    print_frequencies(token_dict)


if __name__ == "__main__":
    main()