import os

import numpy
from scipy import stats
from data_parser import client_server

from data_parser.client_server.data_generation import generate_data

from utilities.utils import sync_files, print_message


def parse_monitor_log(input_files_dir, line_counter):
    if not input_files_dir:
        print 'Please supply the directory that contains observer results'
        return

    original_file_dir = input_files_dir
    parsed_file_dir = original_file_dir + "parsed_results/"

    if not os.path.exists(parsed_file_dir):
        os.makedirs(parsed_file_dir)

    files = [f for f in os.listdir(original_file_dir)
             if f.startswith('observer_log')]

    for i in xrange(len(files)):
        file_name = files[i]
        sub_folder_name = file_name[0: file_name.rfind('.')]

        if not os.path.exists(sub_folder_name):
            os.makedirs(sub_folder_name)

        metric_name = None

        # keep track of last metric id
        # in order to save reading of last metric when
        # encounter new metric
        last_metric_id = None

        metric_value = None
        timestamps = None
        vm_id = None

        # In case the file begin with half of one record, use a flag to
        # indicate the next 'first line' of one record
        # e.g.
        # "f707d0a3-c7a3-4664-b74a-1fc7bcd5d7db	ObserverReceivedTimesampt
        # 1406112134817"
        # Then we can start reading data from this line afterwards
        need_to_skip_to_the_next = False

        # debug
        file_path = os.path.abspath(original_file_dir + '/' + file_name)

        with open(file_path) as test_f:
            print_message('File length: %s' % (len(test_f.readlines())))
            print_message('Line counter %s\n' % line_counter)

        # counter to skip to the last
        with open(file_path) as f:

            # count = 0  # counter for skip to the line left over last time
            # while count < line_counter:
            #     try:
            #         f.next()
            #     except StopIteration as e:
            #         # print 'StopIteration\n' + str(e.message)
            #         count += 1
            #     count += 1

            # current_line = 1  # default to 1 to enable the while loop

            count = 0  # counter for skip to the line left over last time
            if line_counter != 0:
                for current_line in f:
                    if count == int(line_counter):
                        break
                    count += 1

            # Skip to the line after ObserverReceivedTimestamp
            for current_line in f:
                line_counter += 1
                line_segments = current_line.split("\t")
                if len(line_segments) < 3:
                    continue
                if 'ObserverReceivedTimesampt' in line_segments[1]:
                    break

            # The csparql log sometimes contain entries with "MonitorDatum"
            # entries mixed up, hence we explicitly set the program to expect
            # metrics in the expected order and skip those mixed entries
            # since it is way to difficult to parse it for external program
            # like this one and it is actually the job of the csparql
            # observer to print metrics in a consistent format which on the
            # other hand is the efficient fix of this issue
            expected_properties = ['isAbout', 'isProducedBy',
                                   'hasMonitoredMetric', 'hasValue',
                                   'hasTimeStamp']
            expected_prop_counter = 0  # counter to keep track of order of
                                       # expected properties encountered

            for current_line in f:
                line_counter += 1

                # parse current line of the file
                # current_line = f.readline()
                # line_counter += 1

                # [metric_id, metric_prop, value, dump]
                # = current_line.split("\t")
                line_segments = current_line.split("\t")
                if len(line_segments) < 3:
                    continue

                metric_id = line_segments[0]
                metric_prop = line_segments[1]
                value = line_segments[2]

                # if the line is not about metric continue to read next line
                if 'MonitoringDatum' not in metric_id:
                    continue

                # For the first time
                if not last_metric_id:
                    last_metric_id = metric_id

                # check the metric property is currently expected
                # and the metric id is the same one as the one that we'd been
                # reading other expected properties for
                # Even the metric property is currently expected the
                # 'MonitorDatum' ID might be wrong as well
                if metric_prop != expected_properties[expected_prop_counter] or\
                   (expected_prop_counter != 0 and metric_id != last_metric_id):
                    # Skip to the next 'isAbout' line
                    expected_prop_counter = 0  # expecting the 'isAbout'
                    continue

                # if the metric property is expected then expect the next one
                if expected_prop_counter == len(expected_properties) - 1:
                    expected_prop_counter = 0
                else:
                    expected_prop_counter += 1

                # save reading of last metric since following reading
                # will be of a new metric id
                if last_metric_id != metric_id:
                    # check whether any of the 4 properties :
                    # vm_id, metric name, metric value, timestamp
                    # is none, which means that the very end of the file
                    # has one record that is only partially written, hence
                    # ignore this record

                    # if vm_id and metric_name and metric_value and timestamps:

                    result_dir_path = parsed_file_dir + sub_folder_name + \
                                      '/' + vm_id
                    if not os.path.exists(result_dir_path):
                        os.makedirs(result_dir_path)

                    result_file_path = result_dir_path + '/' + \
                                       metric_name + '.txt'
                    with open(result_file_path, 'a') as parsed_f:
                        parsed_f.write(metric_value + '\n')
                        parsed_f.write(timestamps + '\n')

                    # current metric become the last after finish
                    # processing its value
                    last_metric_id = metric_id

                if metric_prop == "isAbout":
                    vm_id = value.replace("Compute#", "")
                elif metric_prop == "hasMonitoredMetric":
                    metric_name = value.replace("QoSMetric#", "")
                elif metric_prop == "hasValue":
                    metric_value = value
                elif metric_prop == "hasTimeStamp":
                    timestamps = value

            # record the position left over
            # line_counter = f.tell()

    return parsed_file_dir, line_counter


def calculate_metrics(data_list):
    """
    Function to calculate metrics needed for optimisation.

    What needs to be calculated:
    1. The total number of requests
    2. Requests arrival rate of the station (lambda)
    3. Service Rate of the station (mu)

    :param data_list:  list of data for each server in current service station
    :return:           tuple of metric (total_request, lambda, mu)
    """
    total_requests = 0
    service_rate = 0

    for data in data_list:
        for i in xrange(len(data[2])):
            total_requests += len(data[2][i])

    # calculate overall arrival rates
    # the length of data[0][0] is the number of sampling time

    avg_arrival_rate = []  # list that stores the average arrival rate
                           # of each server
    for data in data_list:
        avg_arrival_rates_list = []  # list that stores the average arrival
                                     # rate of each sampling interval for
                                     # a single server

        # sum the arrival rate for each request at the same sampling interval
        for i in xrange(len(data[0][0])):
            one_sampling_interval = 0
            for j in xrange(len(data[2]) - 1):
                one_sampling_interval += data[7][j][i]

            # store overall arrival rate of each sampling interval
            # in order to estimate service rate with CPU utilisation
            # which is also collected during each sampling interval
            avg_arrival_rates_list.append(one_sampling_interval)

        # collect average arrival rate of each sever
        # for overall arrival rate calculation
        avg_arrival_rate.append(numpy.mean(avg_arrival_rates_list))

        # estimate service rate regression
        cpu_utils = data[1][len(data[1])-1]

        slope, intercept, r_value, p_value, std_err = \
            stats.linregress(avg_arrival_rates_list, cpu_utils)

        # The overall service rate of the service station is the
        # sum of server rate of each server, since both servers are
        # serving requests simultaneously
        service_rate += slope

    # For the similar reason, the arrival rate is the sum of arrival rate of
    # all servers in the service station.
    arrival_rate = sum(avg_arrival_rate)

    return total_requests, arrival_rate, service_rate


def process_monitor_log(base_dir, observer_addr, line_counter, queue):
    """Parse the monitor log and calculate various metric for all servers in
    the service station monitored by the observer

    :param base_dir:
    :param observer_addr:
    :param line_counter:
    :param queue:
    :return: tuple of metrics needed for optimisation
    """

    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    monitor_log_path = base_dir + 'observer_log.txt'
    station_name, observer_ip = observer_addr.split('=')
    # Flag indicates whether the log contains useful data or not
    log_has_info = False

    while not log_has_info:

        print '\nSynchronising log from observer at: %s' % observer_ip

        module_path = os.path.dirname(client_server.__file__)
        private_key_file_path = module_path + '/logs/ec2_private_key'

        sync_files(host_ip=observer_ip, username='ubuntu',
                   host_file_path='~/results.txt',
                   pk_path=private_key_file_path, dst_loc=monitor_log_path)

        parsed_log_dir, line_counter = parse_monitor_log(base_dir,
                                                         int(line_counter))

        result_queue = generate_data(parsed_log_dir, 2)

        # observer log has contain ResponseInfo if the queue if not empty
        if not result_queue.empty():
            log_has_info = True

    data_list = []
    while not result_queue.empty():
        server_data = result_queue.get()
        data_list.append(server_data)

    total_requests, arrival_rate, service_rate = calculate_metrics(data_list)

    queue.put('%s,%s,%s,%s,%s' % (station_name, total_requests, arrival_rate,
                                  service_rate, line_counter))


# if __name__ == '__main__':
#     # parse_monitor_log('2014_0701_1034')
#     # for i in xrange(len(sys.argv)):
#     # print sys.argv[i]
#     process_monitor_log(sys.argv[1], 0)