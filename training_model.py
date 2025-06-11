import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib # To save/load the model
import re
import jellyfish
from thefuzz import fuzz

# Assuming generate_features is defined in this file or imported from app.py
# Copy the generate_features function from app.py here for standalone training
def generate_features(username, employee_name, first_name, last_name, emp_id):
    username_lower = str(username).lower().strip()
    employee_name_lower = str(employee_name).lower().strip()
    first_name_lower = str(first_name).lower().strip()
    last_name_lower = str(last_name).lower().strip()

    username_cleaned = re.sub(r'[^a-z0-9]', '', username_lower)
    username_no_dot = username_lower.replace('.', '')

    features = {}

    features['fuzz_ratio_full'] = fuzz.ratio(username_lower, employee_name_lower)
    features['fuzz_partial_full'] = fuzz.partial_ratio(username_lower, employee_name_lower)
    features['fuzz_token_sort_full'] = fuzz.token_sort_ratio(username_lower, employee_name_lower)
    features['fuzz_token_set_full'] = fuzz.token_set_ratio(username_lower, employee_name_lower)

    username_parts = re.split(r'[._\s]', username_lower)
    username_potential_first = ""
    username_potential_last = ""
    if len(username_parts) > 1:
        username_potential_first = username_parts[-1]
        username_potential_last = username_parts[0]
    elif len(username_parts) == 1:
        username_potential_first = username_parts[0]
        username_potential_last = username_parts[0]

    features['fuzz_ratio_username_first_to_emp_first'] = fuzz.ratio(username_potential_first, first_name_lower)
    features['fuzz_ratio_username_last_to_emp_last'] = fuzz.ratio(username_potential_last, last_name_lower)
    features['fuzz_ratio_username_first_to_emp_last'] = fuzz.ratio(username_potential_first, last_name_lower)
    features['fuzz_ratio_username_last_to_emp_first'] = fuzz.ratio(username_potential_last, first_name_lower)

    features['fuzz_ratio_cleaned_username_to_emp_name_no_space'] = fuzz.ratio(username_cleaned, employee_name_lower.replace(' ', ''))
    features['fuzz_token_set_cleaned_username_to_emp_name_no_space'] = fuzz.token_set_ratio(username_cleaned, employee_name_lower.replace(' ', ''))
    features['fuzz_ratio_no_dot_username_to_emp_name_no_space'] = fuzz.ratio(username_no_dot, employee_name_lower.replace(' ', ''))

    try:
        features['jelly_soundex_username_last'] = int(jellyfish.soundex(username_potential_last) == jellyfish.soundex(last_name_lower))
        features['jelly_metaphone_username_last'] = int(jellyfish.metaphone(username_potential_last) == jellyfish.metaphone(last_name_lower))
    except Exception:
        features['jelly_soundex_username_last'] = 0
        features['jelly_metaphone_username_last'] = 0

    try:
        features['jelly_soundex_username_first'] = int(jellyfish.soundex(username_potential_first) == jellyfish.soundex(first_name_lower))
        features['jelly_metaphone_username_first'] = int(jellyfish.metaphone(username_potential_first) == jellyfish.metaphone(first_name_lower))
    except Exception:
        features['jelly_soundex_username_first'] = 0
        features['jelly_metaphone_username_first'] = 0

    try:
        features['jelly_soundex_full'] = int(jellyfish.soundex(username_lower) == jellyfish.soundex(employee_name_lower))
        features['jelly_metaphone_full'] = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(employee_name_lower))
    except Exception:
        features['jelly_soundex_full'] = 0
        features['jelly_metaphone_full'] = 0

    features['exact_match_username_to_emp_name'] = int(username_lower == employee_name_lower)
    features['exact_match_username_no_dot_to_emp_name_no_space'] = int(username_no_dot == employee_name_lower.replace(' ', ''))
    features['exact_match_first_name_in_username'] = int(first_name_lower in username_lower or username_lower in first_name_lower)
    features['exact_match_last_name_in_username'] = int(last_name_lower in username_lower or username_lower in last_name_lower)

    numbers_in_username = re.findall(r'\d+', username_lower)
    features['id_match_bonus'] = int(str(emp_id).lower() in numbers_in_username)

    features['len_diff_username_emp_name'] = abs(len(username_lower) - len(employee_name_lower))
    features['len_ratio_username_emp_name'] = min(len(username_lower), len(employee_name_lower)) / (max(len(username_lower), len(employee_name_lower)) + 1e-6)

    return features

def train_and_save_model(data_path="labeled_data.csv", model_filename="fuzzy_match_model.joblib", feature_columns_filename="feature_columns.joblib"):
    # Load your manually labeled data
    # This CSV should have columns: 'username', 'emp_id', 'emp_name', 'first_name', 'last_name', 'is_match' (1 or 0)
    try:
        labeled_df = pd.read_csv(data_path)
    except FileNotFoundError:
        print(f"Error: Labeled data file '{data_path}' not found.")
        print("Please create a CSV file with columns: 'username', 'emp_id', 'emp_name', 'first_name', 'last_name', 'is_match'.")
        print("Populate 'is_match' with 1 for a true match and 0 for a non-match.")
        return

    print("Generating features...")
    # Generate features for all labeled data
    feature_list = labeled_df.apply(
        lambda row: generate_features(
            row['username'],
            row['emp_name'],
            row['first_name'],
            row['last_name'],
            row['emp_id']
        ), axis=1
    ).tolist()

    features_df = pd.DataFrame(feature_list)
    labels = labeled_df['is_match']

    # Handle potential missing features if any
    # This is important to ensure consistency between training and prediction
    feature_columns = features_df.columns.tolist()
    joblib.dump(feature_columns, feature_columns_filename) # Save feature order

    X_train, X_test, y_train, y_test = train_test_split(features_df, labels, test_size=0.2, random_state=42, stratify=labels)

    # Initialize and train the model
    # RandomForestClassifier is a good choice for robustness
    model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced') # 'balanced' helps with imbalanced datasets
    print("Training model...")
    model.fit(X_train, y_train)

    # Evaluate the model
    y_pred = model.predict(X_test)
    print("\nModel Evaluation:")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(classification_report(y_test, y_pred))

    # Save the trained model
    joblib.dump(model, model_filename)
    print(f"\nModel saved to {model_filename}")
    print(f"Feature columns saved to {feature_columns_filename}")

if __name__ == "__main__":
    train_and_save_model()