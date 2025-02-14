import sys
import os
import re

Token = str  # Type alias for clarity


def tokenize(file_path: str) -> list[Token]:
    """
    Reads a text file and returns a list of tokens (words).
    A token is defined as a sequence of alphanumeric characters.
    For small files, the entire content is read into memory;
    for large files (≥ 100 MB), the file is processed line by line.

    Args:
        file_path (str): Path to the text file.

    Returns:
        list[Token]: A list of tokens extracted from the file.
    """
    try:
        file_size = os.path.getsize(file_path)
        threshold = 100 * 1024 * 1024  # 100 MB threshold
        tokens = []

        if file_size < threshold:
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
                # Replace non-alphanumeric characters with a space,
                # convert to lowercase, then extract tokens.
                text = re.sub(r'[^a-zA-Z0-9]', ' ', text.lower())
                tokens = re.findall(r'[a-zA-Z0-9]+', text)
        else:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    line = re.sub(r'[^a-zA-Z0-9]', ' ', line.lower())
                    tokens.extend(re.findall(r'[a-zA-Z0-9]+', line))
        return tokens

    except UnicodeDecodeError:
        print(f"Warning: Skipping bad input in file '{file_path}'.")
        return []
    except Exception as e:
        # Instead of printing the full error (which might be extremely long),
        # print a concise message.
        print("Error: An unexpected error occurred while processing the file.")
        return []


def compute_word_frequencies(tokens: list[Token]) -> dict[Token, int]:
    """
    Uses the tokenized list and adds them to a frequency dictionary.

    Args:
        tokens (list[Token]): A list of tokens.

    Returns:
        dict[Token, int]: A dictionary where keys are tokens and values are their frequencies.
    """
    token_dict = {}
    for token in tokens:
        token_dict[token] = token_dict.get(token, 0) + 1
    return token_dict


def print_frequencies(frequencies: dict[Token, int]) -> None:
    """
    Prints sorted tokens in the format "word -> frequency".
    Sorting is done by decreasing frequency and alphabetically for ties.

    Args:
        frequencies (dict[Token, int]): A dictionary of token frequencies.
    """
    sorted_tokens = sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
    for token, freq in sorted_tokens:
        print(f"{token} -> {freq}")


def main():
    """
    Reads a file path from the command line, tokenizes the file content,
    computes word frequencies, and prints them.
    """
    if len(sys.argv) != 2:
        print("Usage: python my_tokenizer.py <text_file>")
        sys.exit(1)

    file_path = sys.argv[1]
    tokens = tokenize(file_path)
    token_dict = compute_word_frequencies(tokens)
    print_frequencies(token_dict)


if __name__ == "__main__":
    main()
