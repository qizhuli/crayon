# Flask app server
from flask import Flask, request, json, Response
app = Flask("tensorboardhttpapi")

# HTTP client to use the tensorboard api
import urllib2

# Not-supported logging types
not_supported_types = [
  "audio",
  "compressedHistograms",
  "graph",
  "images",
  "meta_graph",
  "run_metadata"]

# Tensorboard includes
import tensorflow as tf
import bisect

### Tensorboard utility functions
xp_writers = {}
def tb_get_xp_writer(experiment):
  if experiment in xp_writers:
    return xp_writers[experiment]

  xp_folder = "/tmp/tensorboard/{}".format(experiment)
  writer = tf.summary.FileWriter(xp_folder, flush_secs=1)
  xp_writers[experiment] = writer
  return writer

def tb_add_scalar(experiment, name, wall_time, step, value):
  writer = tb_get_xp_writer(experiment)
  summary = tf.Summary(value=[
      tf.Summary.Value(tag=name, simple_value=value),
  ])
  event = tf.Event(wall_time=wall_time, step=step, summary=summary)
  writer.add_event(event)
  writer.flush()

def tb_add_histogram(experiment, name, wall_time, step, histo):
  writer = tb_get_xp_writer(experiment)
  summary = tf.Summary(value=[
      tf.Summary.Value(tag=name, histo=histo),
  ])
  event = tf.Event(wall_time=wall_time, step=step, summary=summary)
  writer.add_event(event)
  writer.flush()

def tb_request(type, run, tag):
  request_url = "http://localhost:8888/data/{}"
  if run and tag:
    request_url += "?run={}&tag={}"

  request_url = request_url.format(type, run, tag)
  try:
    return urllib2.urlopen(request_url, timeout=1).read()
  except:
    message = "Combination of experiment '{}' and name '{}' does not exist".format(run, tag)
    return wrong_argument(message)

# Borrowed from tensorflow/tensorboard/scripts/generate_testdata.py
# Create a histogram from a list of values
def _MakeHistogramBuckets():
  v = 1E-12
  buckets = []
  neg_buckets = []
  while v < 1E20:
    buckets.append(v)
    neg_buckets.append(-v)
    v *= 1.1
  # Should include DBL_MAX, but won't bother for test data.
  return neg_buckets[::-1] + [0] + buckets


def tb_make_histogram(values):
  """Convert values into a histogram proto using logic from histogram.cc."""
  limits = _MakeHistogramBuckets()
  counts = [0] * len(limits)
  for v in values:
    idx = bisect.bisect_left(limits, v)
    counts[idx] += 1

  limit_counts = [(limits[i], counts[i]) for i in xrange(len(limits))
                  if counts[i]]
  bucket_limit = [lc[0] for lc in limit_counts]
  bucket = [lc[1] for lc in limit_counts]
  sum_sq = sum(v * v for v in values)
  return {
      "min": min(values),
      "max": max(values),
      "num": len(values),
      "sum": sum(values),
      "sum_squares": sum_sq,
      "bucket_limit": bucket_limit,
      "bucket": bucket}
## END of borrowed


### Error handler
@app.errorhandler(404)
def not_found(error):
  return "This is not the web page you are looking for."

def wrong_argument(message):
  print("wrong_argument: ", message)
  return message, 400

### Experience management
@app.route('/data')
def get_all_experiments():
  experiment = request.args.get('xp')

  result = ""
  req_res = tb_request("runs")
  if not isinstance(req_res, str):
    return req_res
  tb_data = json.loads(req_res)
  print(experiment)
  if experiment:
    if experiment in tb_data:
      result = tb_data[experiment]
      # Remove the not supported types from the answer
      for not_supported_type in not_supported_types:
        if not_supported_type in result:
          del result[not_supported_type]
      result = json.dumps(result)
    else:
      return wrong_argument("Unknown experiment name '{}'".format(experiment))
  else:
    result = json.dumps(tb_data.keys())

  return result 

### Scalar data
@app.route('/data/scalars', methods=["GET"])
def get_scalars():
  experiment = request.args.get('xp')
  name = request.args.get('name')
  if (not experiment) or (not name):
    return wrong_argument("xp and name arguments are required")

  return tb_request("scalars", experiment, name)

@app.route('/data/scalars', methods=['POST'])
def post_scalars():
  experiment = request.args.get('xp')
  name = request.args.get('name')
  if (not experiment) or (not name):
    return wrong_argument("xp and name arguments are required")

  if not len(request.form.keys()) == 1:
    return wrong_argument("POST content is not correct: {}".format(request.form.keys()))
  data = json.loads(request.form.keys()[0])
  if (not data) or (not len(data)==3):
    return wrong_argument("POST does not contain a list of 3 elements but '{}'".format(data))

  tb_add_scalar(experiment, name, data[0], data[1], data[2])

  return "ok"


### Histogram data
@app.route('/data/histograms', methods=["GET"])
def get_histograms():
  experiment = request.args.get('xp')
  name = request.args.get('name')
  if (not experiment) or (not name):
    return wrong_argument("xp and name arguments are required")

  return tb_request("histograms", experiment, name)

@app.route('/data/histograms', methods=['POST'])
def post_histograms():
  experiment = request.args.get('xp')
  name = request.args.get('name')
  to_build = request.args.get('tobuild')
  if (not experiment) or (not name) or (not to_build):
    return wrong_argument("xp, name and tobuild arguments are required")
  to_build = to_build == "true"

  if not len(request.form.keys()) == 1:
    return wrong_argument("POST content is not correct: {}".format(request.form.keys()))
  data = json.loads(request.form.keys()[0])
  if (not data) or (not len(data)==3):
    return wrong_argument("POST does not contain a list of 3 elements but '{}'".format(data))

  if to_build:
    if (not data[2]) or (not isinstance(data[2], list)):
      return wrong_argument("elements to build the histogram are not in a list but '{}'".format(data[2]))
    histogram_dict = tb_build_histogram(data[2])
  else:
    already_built_required_params = {
      "min": [float, int],
      "max": [float, int],
      "num": [int],
      "bucket_limit": [list],
      "bucket": [list],
    }
    histogram_dict = data[2]
    for required_param in already_built_required_params:
      if not (required_param in histogram_dict):
        message = "Missing argument {} to the given histogram".format(required_param)
        return wrong_argument(message)
      is_ok = False
      for required_type in already_built_required_params[required_param]:
        if isinstance(histogram_dict[required_param], required_type):
          is_ok = True
          break
      if not is_ok:
        message = "Argument {} should be of type {} and is {}"
        message = message.format(required_param, str(already_built_required_params[required_param]), str(type(histogram_dict[required_param])))
        return wrong_argument(message)

  tb_add_histogram(experiment, name, data[0], data[1], histogram_dict)

  return "ok"


app.run(host="0.0.0.0", port=8889)
