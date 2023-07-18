# HTTP Segment

This is a simple service that wraps the [`yolov8x-seg` model](https://docs.ultralytics.com/tasks/segment/)
in an HTTP API based on the Starlette framework.

|                                |                                          |
| ------------------------------ | ---------------------------------------- |
| ![](./.github/readme/test.png) | ![](./.github/readme/test_segmented.png) |

## Usage

This app can be run with `make run` or with Docker:

```sh
docker build -t $IMAGE_NAME .
docker run -p 8000:8000 $IMAGE_NAME
```

By specifying the `MODEL` environment variable you can change the model loaded
by the service. The default is `yolov8x-seg`.

### Configuration

The following environment variables should be used to configure the service:

- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_BUCKET`
- `S3_ENDPOINT_URL`

### Endpoints

#### `/segment`

Accepts a POST request with a an image in the body of the request.

It will then perform segmentation on the image, upload the segmented images to
S3 and return a JSON response with the URLs of the uploaded images, including
the original.

```sh
curl -X POST --data-binary @./.github/readme/test.png http://localhost:8000/segment

{"file_names":["209d43982bc349299f45234071d1dd3d.webp","eb4c8fe8636648b790741ff29351fbf6.webp"]}
```

#### `/segment/{resize:int}`

The same as `/segment` but will resize the cropped images to the specified
size, upscaling if necessary.

```sh
curl -X POST --data-binary @./.github/readme/test.png http://localhost:8000/segment/256

{"file_names":["209d43982bc349299f45234071d1dd3d.webp","eb4c8fe8636648b790741ff29351fbf6.webp"]}
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
