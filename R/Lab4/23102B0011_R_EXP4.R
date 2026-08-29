
# Load Packages


library(jpeg)
library(keras3)


# Image Files


pics <- c(
  "p1.jpg", "p2.jpg", "p3.jpg",
  "p4.jpg", "p5.jpg", "p6.jpg",
  "c1.jpg", "c2.jpg", "c3.jpg",
  "c4.jpg", "c5.jpg", "c6.jpg"
)

# Read Images


mypic <- list()

for (i in 1:12) {
  mypic[[i]] <- readJPEG(pics[i])
}

# Check image dimensions
dim(mypic[[1]])


# 
# Resize Function
# 

resize_image <- function(img, new_height = 28, new_width = 28) {

  old_height <- dim(img)[1]
  old_width  <- dim(img)[2]
  channels   <- dim(img)[3]

  result <- array(
    0,
    dim = c(new_height, new_width, channels)
  )

  for (c in 1:channels) {

    for (i in 1:new_height) {

      old_i <- round(
        (i - 1) * (old_height - 1) / (new_height - 1)
      ) + 1

      for (j in 1:new_width) {

        old_j <- round(
          (j - 1) * (old_width - 1) / (new_width - 1)
        ) + 1

        result[i, j, c] <- img[old_i, old_j, c]
      }
    }
  }

  return(result)
}


# 
# Resize All Images
# 

for (i in 1:12) {

  mypic[[i]] <- resize_image(
    mypic[[i]],
    28,
    28
  )

}

# Check
dim(mypic[[1]])

# Should be:
# 28 28 3


# 
# Reshape
# 

for (i in 1:12) {

  mypic[[i]] <- array_reshape(
    mypic[[i]],
    c(1, 2352)
  )

}



# Training Data


trainx <- NULL

# p1 - p5
for (i in 1:5) {
  trainx <- rbind(
    trainx,
    mypic[[i]]
  )
}

# c1 - c5
for (i in 7:11) {
  trainx <- rbind(
    trainx,
    mypic[[i]]
  )
}

str(trainx)



# Test Data


testx <- rbind(
  mypic[[6]],
  mypic[[12]]
)


# Labels


trainy <- c(
  0, 0, 0, 0, 0,
  1, 1, 1, 1, 1
)

testy <- c(0, 1)



# One Hot Encoding


trainLabels <- to_categorical(
  trainy,
  num_classes = 2
)

testLabels <- to_categorical(
  testy,
  num_classes = 2
)



# Model


model <- keras_model_sequential()

model |>
  layer_dense(
    units = 256,
    activation = "relu",
    input_shape = c(2352)
  ) |>
  layer_dense(
    units = 128,
    activation = "relu"
  ) |>
  layer_dense(
    units = 2,
    activation = "softmax"
  )


summary(model)



# Compile


model |>
  compile(
    loss = "categorical_crossentropy",
    optimizer = optimizer_rmsprop(),
    metrics = "accuracy"
  )



# Train


history <- model |>
  fit(
    trainx,
    trainLabels,
    epochs = 30,
    batch_size = 32,
    validation_split = 0.2
  )



# Evaluation


model |>
  evaluate(
    trainx,
    trainLabels
  )



# Prediction


prob <- model |>
  predict(trainx)

pred <- max.col(prob) - 1



# Results


table(
  Predicted = pred,
  Actual = trainy
)

cbind(
  prob,
  Predicted = pred,
  Actual = trainy
)

