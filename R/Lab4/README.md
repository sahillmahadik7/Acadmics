# Image Classification Using R

## Overview
This project implements a basic image classification system using R and deep learning. JPEG images are loaded, resized, converted into numerical features, and used to train a neural network.

## Dataset
The project contains 12 images divided into two classes:

- `p1.jpg` to `p6.jpg` — Class 0
- `c1.jpg` to `c6.jpg` — Class 1

10 images are used for training and 2 images for testing.

## Libraries Used
- `jpeg` — Reads JPEG images.
- `keras3` — Builds and trains the neural network.

## Operations Performed
1. Load images.
2. Resize images to 28 × 28 × 3.
3. Convert images into numerical features.
4. Prepare training and testing data.
5. Build a neural network.
6. Train the model for 30 epochs.
7. Evaluate the model.
8. Predict the classes of test images.

## Files
- `23102B0018_R-EXP4.R` — Main R program.
- `p1.jpg`–`p6.jpg` and `c1.jpg`–`c6.jpg` — Dataset images.
- `model.png` — Neural network/model output.
- `results.png` — Project results.

## How to Run

Install the required packages:

```r
install.packages("jpeg")
install.packages("keras3")
```

Open `23102B0018_R-EXP4.R` in RStudio and run the complete script.

## Output
The project trains an image classification model, evaluates its performance, and predicts the classes of test images.

## Conclusion
This project demonstrates image preprocessing, deep learning, model training, evaluation, and prediction using R.