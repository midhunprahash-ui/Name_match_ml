
# Username Matching - ML Mini Project

## Use Case

This project aims to **predict the most likely employee(s)** behind a given username by analyzing and comparing it against a dataset of employee names. When a user enters a username, the system returns a ranked list of matching employees along with:

- **Employee Name**
- **Employee ID**
- **Probability Score** indicating the likelihood of a match

This can be useful in enterprise systems where usernames are not standardized, or where usernames need to be mapped back to known employee identities.

---

## Role of Machine Learning

A **Random Forest classifier** is trained on a dataset of 40,000 records containing:

- Employee names
- Corresponding possible usernames (realistic or artificial)

Each record is labeled:
- `1` for a **true match** (username corresponds to the employee)
- `0` for a **false match** (username does not belong to the employee)

This allows the model to learn patterns that distinguish realistic username-to-employee matches.

---

## Feature Engineering

To enrich the training data, a variety of string similarity algorithms are used as features:

- **Levenshtein Distance**: Measures character-level edits between strings
- **FuzzyWuzzy Ratios**:
- **partial_ratio**
- **token_set_ratio**
- **Soundex Matching**: Phonetic similarity algorithm
- **Metaphone Matching**: Advanced phonetic algorithm for English

These features allow the model to capture both visual and phonetic similarities, improving prediction accuracy.

---
