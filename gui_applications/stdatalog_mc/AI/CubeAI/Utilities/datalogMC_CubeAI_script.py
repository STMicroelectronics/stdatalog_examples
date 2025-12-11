import sys
import subprocess
import importlib
import os

# Add the STDatalog SDK root directory to the sys.path to access the SDK packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../..')))

import subprocess
import stdatalog_core.HSD_utils.logger as logger
log = logger.setup_applevel_logger(is_debug = False, file_name= "app_debug.log")

def check_and_install(package, version=None, import_name=None):
    """
    Check if a package is installed, and if not, prompt to install it.
    If version is specified, check for the version as well.
    """
    try:
        pkg = importlib.import_module(import_name or package)
        if version:
            pkg_version = getattr(pkg, '__version__', None)
            if pkg_version and pkg_version != version:
                log.warning(f"{package} version {pkg_version} is installed, but version {version} is required.")
                response = input(f"Do you want to install {package}=={version}? [y/N]: ").strip().lower()
                if response == 'y':
                    subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}=={version}"])
            else:
                log.info(f"{package} version {pkg_version} is installed.")
        else:
            log.info(f"{package} is installed.")
    except ImportError:
        log.error(f"{package} is not installed.")
        response = input(f"Do you want to install {package}{'=='+version if version else ''}? [y/N]: ").strip().lower()
        if response == 'y':
            subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}=={version}" if version else package])
        else:
            log.warning(f"Cannot continue without {package}. Exiting.")
            sys.exit(1)

def check_all_dependencies():
    # List of required packages: (pip_name, version, import_name)
    required_packages = [
        {"package": "tensorflow", "version": "2.19.0", "import_name": None},
        {"package": "keras", "version": "3.10.0", "import_name": None},
        {"package": "numpy", "version": "2.2.4", "import_name": None},
        {"package": "pandas", "version": "2.2.3", "import_name": None},
        {"package": "matplotlib", "version": None, "import_name": None},
        {"package": "scikit-learn", "version": None, "import_name": "sklearn"},
        {"package": "seaborn", "version": None, "import_name": None}
    ]

    for pkg in required_packages:
        check_and_install(pkg["package"], version=pkg.get("version"), import_name=pkg.get("import_name"))

# Run dependency check at the very top
check_all_dependencies()

# Now safe to import everything
import tensorflow as tf
import keras
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import argparse 
from sklearn.model_selection import train_test_split
from tensorflow.keras.layers import Conv1D, MaxPooling1D, Flatten, Dense, Dropout, Input
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.utils import to_categorical
from sklearn.metrics import confusion_matrix, classification_report
import seaborn as sns
import os

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

log.info(f"TensorFlow version: {tf.__version__}")
log.info(f"Keras version: {tf.keras.__version__}")

def rearrange_row_channels(row, num_channels=4):
    row = np.array(row)
    n_timesteps = len(row) // num_channels
    arr = row.reshape(n_timesteps, num_channels)
    return arr

def save_data_by_class(data, labels, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    unique_classes = np.unique(labels)
    
    for class_name in unique_classes:
        indices = np.where(labels == class_name)[0]
        class_data = data[indices]  # shape: (num_samples, 1024, 4)
        
        # Flatten each sample
        class_data_flat = class_data.reshape(class_data.shape[0], -1)  # shape: (num_samples, 4096)
        
        df = pd.DataFrame(class_data_flat)
        csv_path = os.path.join(output_dir, f"{class_name}.csv")
        df.to_csv(csv_path, index=False)
        log.info(f"Saved {csv_path}")

def load_data_from_csv(acquisition_folder, num_channels=4):    
    data = []
    labels = []
    
    # 1. Find the "output" folder inside the acquisition folder
    output_folder = None
    try:
        for item in os.listdir(acquisition_folder):
            if item == "output" and os.path.isdir(os.path.join(acquisition_folder, item)):
                output_folder = os.path.join(acquisition_folder, item)
                log.info(f"Found output folder: {output_folder}")
                break
    except FileNotFoundError:
        log.error(f"Error: The folder '{acquisition_folder}' does not exist.")
        sys.exit(1)

    if output_folder is None:
        log.error(f"Error: No 'output' folder found in the acquisition folder.")
        sys.exit(1)
    
    # 2. For each subfolder in the "output" folder
    for subfolder in os.listdir(output_folder):
        subfolder_path = os.path.join(output_folder, subfolder)
        if os.path.isdir(subfolder_path):
            # 3. Search for .csv files in the subfolder
            for file in os.listdir(subfolder_path):
                if file.endswith('.csv'):
                    file_path = os.path.join(subfolder_path, file)
                    class_name = file.split('.')[0]
                    df = pd.read_csv(file_path)
                    for _, row in df.iterrows():
                        rearranged = rearrange_row_channels(row.values, num_channels)
                        data.append(rearranged)
                        labels.append(class_name)
    
    return np.array(data), np.array(labels)

def normalize_per_sample(X):
    mean = X.mean(axis=1, keepdims=True)
    std = X.std(axis=1, keepdims=True)
    std[std == 0] = 1
    normalized_data = (X - mean) / std
    return mean, std, normalized_data

def create_cnn_model(input_shape, output):
    model = Sequential([
        Input(shape=input_shape),
        Conv1D(filters=20, kernel_size=4, strides=1, activation='relu'),
        MaxPooling1D(pool_size=2),
        Dropout(0.25),
        Conv1D(filters=8, kernel_size=4, activation='relu'),
        MaxPooling1D(pool_size=2),
        Dropout(0.25),
        Conv1D(filters=8, kernel_size=4, activation='relu'),
        MaxPooling1D(pool_size=2),
        Dropout(0.25),
        Conv1D(filters=8, kernel_size=4, activation='relu'),
        MaxPooling1D(pool_size=2),
        Dropout(0.25),
        Flatten(),
        Dense(4, activation='relu'),
        Dropout(0.5),
        Dense(output, activation='softmax')
    ])
    model.compile(optimizer=Adam(learning_rate=0.001),
                  loss='sparse_categorical_crossentropy',
                  metrics=['accuracy'])
    return model

def extract_sample_by_class(X, y, class_label, idx):
    idx_Array = np.where(y == class_label)[0]
    if idx > len(idx_Array) or len(idx_Array) == 0:
        raise ValueError(f"No sample found for class {class_label}")
    return idx_Array[idx], X[idx_Array[idx]]

def main():

    # --- Argument parsing ---
    parser = argparse.ArgumentParser(description="Run CNN training on a specified data folder.")
    parser.add_argument(
                        "data_folder",
                        nargs="?",
                        help="Name or path of the acquisition folder")
    
    args = parser.parse_args()
    data_folder = args.data_folder

    # Load and encode data
    data, labels = load_data_from_csv(data_folder)

    save_data_by_class(data, labels, output_dir=os.path.join(script_dir, "separated_classes_original"))
    
    label_encoder = {label: idx for idx, label in enumerate(np.unique(labels))}
    encoded_labels = np.array([label_encoder[label] for label in labels])

    # Shuffle and split
    indices = np.arange(data.shape[0])
    np.random.shuffle(indices)
    data = data[indices]
    encoded_labels = encoded_labels[indices]
    X_train, X_test, y_train, y_test = train_test_split(
        data, encoded_labels, test_size=0.25, stratify=encoded_labels
    )

    log.info("Dataset dimensions:")
    log.info(f"X_test shape: {X_test.shape}")
    log.info(f"y_test shape: {y_test.shape}")
    log.info(f"train set dimension: {X_train.shape}")
    log.info(f"test set dimension: {X_test.shape}")

    # Data normalization
    log.info("Applying per-sample normalization:")
    mean_train, std_train, X_train_scaled = normalize_per_sample(X_train)
    mean_test, std_test, X_test_scaled = normalize_per_sample(X_test)

    # Export test data for CubeAI quantization validation
    y_test_cat = to_categorical(y_test, num_classes=2)
    npz_path = os.path.join(script_dir, "cubeAI_Quantization_TestData.npz")
    np.savez(npz_path, x_test=X_test_scaled, y_test=y_test_cat)
    log.info(f"Test data saved to: {npz_path}")

    # Model definition, training, and evaluation
    input_shape = (1024, 4)
    output_classes = 2
    model = create_cnn_model(input_shape, output_classes)
    model.summary()
    history = model.fit(X_train_scaled, y_train, epochs=200, batch_size=32, validation_split=0.2)
    test_loss, test_accuracy = model.evaluate(X_test_scaled, y_test)
    log.info(f"Test Accuracy: {test_accuracy:.4f}")
    # Save the model in the script's directory
    model_path = os.path.join(script_dir, 'motor_current_cnn_model.h5')
    model.save(model_path)
    log.info(f"Model saved to: {model_path}")

    # Predict and show results for first 20 test samples
    for i in range(20):
        data_point_reshaped = np.expand_dims(X_test_scaled[i], axis=0)
        y_pred = model.predict(data_point_reshaped)
        y_pred_classes = np.argmax(y_pred, axis=1)
        log.info(f"Real class     : {y_test[i]}")
        log.info(f"Predicted class: {y_pred_classes[0]} prob: {y_pred[0][y_pred_classes[0]]}\n")

    # Evaluate and show confusion matrix
    y_pred = model.predict(X_test_scaled)
    y_pred_classes = np.argmax(y_pred, axis=1)
    
    log.info("Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred_classes)

    # Get class labels from label_encoder
    # If label_encoder is a LabelEncoder instance:
    if hasattr(label_encoder, 'classes_'):
        class_labels = label_encoder.classes_
    # If label_encoder is a dict or mapping:
    elif hasattr(label_encoder, 'keys'):
        class_labels = list(label_encoder.keys())
    else:
        class_labels = None  # fallback

    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=class_labels, yticklabels=class_labels)
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title('Confusion Matrix')
    plt.tight_layout()
    plt.show()  

    log.info("Classification Report:")
    log.info(classification_report(y_test, y_pred_classes, target_names=label_encoder.keys()))

if __name__ == "__main__":
    main()