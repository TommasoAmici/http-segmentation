# HTTP Segment

This is a simple service that wraps the [`yolov8x-seg` model](https://docs.ultralytics.com/tasks/segment/)
in an HTTP API based on the Starlette framework.

## Usage

This app can be run with `make run` or with Docker:

```sh
docker build -t $IMAGE_NAME .
docker run -p 8000:8000 $IMAGE_NAME
```

By specifying the `MODEL` environment variable you can change the model loaded
by the service. The default is `yolov8x-seg`.

### Endpoints

#### `/segment`

Accepts a POST request with a an image in the body of the request.

It will then perform segmentation on the image and if there is only one mask
it will return the segmented image as a webp. If there are multiple masks it
will return a `multipart/form-data` response containing all the segmented images.

You should inspect the `content-type` header of the response to determine
whether the response contains a single image or multiple images.

```sh
curl -X POST --data-binary @./.github/readme/test.png \
  http://localhost:8000/segment
```

| Request                        | Response                                 |
| ------------------------------ | ---------------------------------------- |
| ![](./.github/readme/test.png) | ![](./.github/readme/test_segmented.png) |

#### `/segment/{resize:int}`

The same as `/segment` but will resize the cropped images to the specified
size.

```sh
curl -X POST --data-binary @./.github/readme/test.png \
  http://localhost:8000/segment/256
```

#### `/health`

Returns a 200 response if the service is healthy. This is a bit of a weird
healthcheck since it will return a 500 if two minutes have passed since the last
request. This can be used to determine if the service is still running but
hasn't received any requests in a while.

Since the AI model is loaded into memory when the first request is received,
rather than at startup, this endpoint can be used to restart the service and
free memory after a period of inactivity.

I built this mechanism because I don't expect this service to be used very
often and I want to keep memory in check.

```sh
curl http://localhost:8000/health
```
