from __future__ import division
from cvxopt import matrix, solvers
import math

from utilities.utils import print_message


def f_range(start, stop, step):
    """
    Generate sequence of value with float step
    :param start:
    :param stop:
    :param step:
    :return:
    """
    r = float(start)
    while r < float(stop):
        yield r
        r += float(step)


def optimise(num_of_stations, total_requests, elb_prices,
             avg_data_in_per_reqs, avg_data_out_per_reqs,
             in_bandwidths, out_bandwidths, budget, sla_response_t,
             service_rates, measurement_interval, station_latency, k,
             ec2_prices_ranges=None, cost_mode=None):
    """
    :param num_of_stations: total number of receipts of client requests
    :param total_requests:  total number of requests generated by client
    :param elb_prices:      list of pricing of every ELB involved

    :param avg_data_in_per_reqs:    the average amount of data transferred in
                                    pre request for requests received at
                                    *each service station*

    :param avg_data_out_per_reqs:   the average amount of data transferred out
                                    pre request for requests received at
                                    *each service station*

    :param in_bandwidths:   The capacity of the link used by each service
                            station to receive request
    :param out_bandwidths:  The capacity of the link used by each service
                            station to send response

    :param service_rates:   Overall service rate of each service station
    :param station_latency: latency between this client and each station
    :param sla_response_t:  Service Level Agreement of the response time
                            for each service station

    :param budget:          Budget of the OSP

    :param k:               coefficient to reflect on how much additional
                            cost to pay for one unit of throughput improvement

    :param measurement_interval: The length of measurement time (in seconds)

    :param ec2_prices_ranges:   The price charged by EC2 based on different
                                amount of data sent out of EC2 (Dict of dict)
    :param cost_mode:           Mode for selecting different EC2 data trans

    :return:                The current best weight for each requests receipt

    # Objective: (e.g number of service station = 2)
    # maximise  Cost + K * throughput
    #
    ///////////////////
     Update: New objective function:
             Minimise Cost + latency perceived by user
             latency perceived by user

     Only the objective function and response time constrain needs to change
    ////////////////////
    #
    #         ************ Deprecated *************
    #
    #         total_requests *
    #         (avg_data_in_per_req[0] + avg_data_out_per_req[0]) *
    #         elb_price[0] *
    #         P[0]
    #         +
    #         total_requests * avg_data_out_per_req[0] * P[0] * ec2_price_range
    #         +
    #         K * total_requests *
    #         P[0]

    #         +

    #         total_requests *
    #         (avg_data_in_per_req[1] + avg_data_out_per_req[1]) *
    #         elb_price[1] *
    #         P[1]
    #         +
    #         total_requests * avg_data_out_per_req[0] * P[0] * ec2_price_range
    #         +
    #         K * total_requests *
    #         P[1]

    #         "Actually formulation":

    #         (total_requests *
    #         (avg_data_in_per_req[0] + avg_data_out_per_req[0]) *
    #         elb_price[0]
    #         +
    #         K * total_requests
    #         +
    #         total_requests * avg_data_out_per_req[0] * ec2_price_range) * P[0]
    #
    #         +
    #
    #         (total_requests *
    #         (avg_data_in_per_req[1] + avg_data_out_per_req[1]) *
    #         elb_price[1]
    #         +
    #         K * total_requests
    #         +
    #         total_requests * avg_data_out_per_req[1] * ec2_price_range) * P[1]
    #
    #         ************ End of Deprecated *************
    #
    # Subject to:

    #   "data_in/second < bandwidth of the in_link"

    #   (total_requests * avg_data_in_per_req[0] * P[0]))
    #   / measurement_interval < in_bandwidth[0]

    #   (total_requests * avg_data_in_per_req[1] * P[1]))
    #   / measurement_interval < in_bandwidth[1]

    #   "data_out/second < bandwidth of the out_link"

    #   (total_requests * avg_data_out_per_req[0] * P[0]))
    #   / measurement_interval < out_bandwidth[0]

    #   (total_requests * avg_data_out_per_req[1] * P[1]))
    #   / measurement_interval < out_bandwidth[1]

    #   "Actually formulation":
    #
    #   total_requests * avg_data_in_per_req[0] / measurement_interval * P[0] +
    #                    0                                             * P[1]
    #                                                      <= in_bandwidth[0]

    #                    0                                             * P[0] +
    #   total_requests * avg_data_in_per_req[1] / measurement_interval * P[1]
    #                                                      <= in_bandwidth[1]

    #   total_requests * avg_data_out_per_req[0] / measurement_interval * P[0] +
    #                    0                                              * P[1]
    #                                                      <= out_bandwidth[0]

    #                    0                                              * P[0] +
    #   total_requests * avg_data_out_per_req[1] / measurement_interval * P[1]
    #                                                      <= out_bandwidth[1]



    #   "(Deprecated)Response time constrain"

    #   D_sla[0] * service_rates[0]^-1 * total_requests * P[0]
    #           <= measurement_interval * (D_sla[0] - service_rates[0]^-1)

    #   D_sla[1] * service_rates[1]^-1 * total_requests * P[1]
    #           <= measurement_interval * (D_sla[1] - service_rates[1]^-1)

    #   "Actually formulation":

    #   D_sla[0] * service_rates[0]^-1 * total_requests * P[0] +
    #                    0                              * P[1]
    #           <= measurement_interval * (D_sla[0] - service_rates[0]^-1)

    #                    0                              * P[0] +
    #   D_sla[1] * service_rates[1]^-1 * total_requests * P[1]
    #           <= measurement_interval * (D_sla[1] - service_rates[1]^-1)


    #   "Budget of OSP" (EC2 cost is calculated differently)
    #   total_requests * (avg_data_in_per_reqs[0] +
    #                     avg_data_out_per_reqs[0]) * elb_prices[0] * P[0]
    #   +
    #
    #   total_requests * (avg_data_in_per_reqs[1] +
    #                     avg_data_out_per_reqs[1]) * elb_prices[1] * P[1]
    #           <= budget


    #   "Sum of weights is 1"
    #   P[0] + P[1] + ... P[num Of Servers - 1] = 1

    #   "P are all positive"
    #   1 * P[0] + 0 * P[1] + 0 * P[2] .... > 0
    #   0 * P[0] + 1 * P[1] + 0 * P[2] .... > 0
    #   0 * P[0] + 0 * P[1] + 1 * P[2] .... > 0
    #   ... ...
    #
    # Variable: P[i]
    """

    coefficients = []
    # right hand side of constrains
    right_hand_side = []
    # coefficients in objective function
    obj_func_coef = []

    for i in xrange(num_of_stations):
        # Building coefficients for constrains inequations.

        # Collecting coefficients of each variable of each constrains inequation

        """ In bandwidth constrains """
        # | t*a/m  0    0    0   ... | < in_bandwidth[0]
        # |   0  t*a/m  0    0   ... | < in_bandwidth[1]
        # |   0    0  t*a/m  0   ... | < in_bandwidth[2]
        # |   0    0    0  t*a/m ... | ... ...
        in_bandwidth_coef = [0 for i1 in xrange(num_of_stations)]
        in_bandwidth_coef[i] = \
            total_requests * avg_data_in_per_reqs[i] / measurement_interval

        """ Out bandwidth constrains """
        out_bandwidth_coef = [0 for i2 in xrange(num_of_stations)]
        out_bandwidth_coef[i] = \
            total_requests * avg_data_out_per_reqs[i] / measurement_interval

        # """ Response time constrain """
        response_t_coef = [0 for i3 in xrange(num_of_stations)]
        response_t_coef[i] = \
            sla_response_t[i] * math.pow(service_rates[i], -1) * total_requests

        """ All variable (weights) are positive """
        all_pos_coef = [0 for i4 in xrange(num_of_stations)]
        all_pos_coef[i] = -1  # convert to standard form

        """ coefficient for the "sum of weights is 1" constrain (i.e all 1) """
        sum_p_coef = 1

        """ Cost less then or equal to budget """

        cost_coef = \
            total_requests * (avg_data_in_per_reqs[i] +
                              avg_data_out_per_reqs[i]) * elb_prices[i] + \
            0.120 * total_requests * avg_data_out_per_reqs[i]

        #### test ####
        print_message('Total cost : $%s' % cost_coef)
        #### test ####

        # Store all coefficients for this variable in the above order
        """ Order matters """
        coefficients_for_p_i = []
        coefficients_for_p_i.extend(in_bandwidth_coef)
        coefficients_for_p_i.extend(out_bandwidth_coef)
        coefficients_for_p_i.extend(response_t_coef)
        coefficients_for_p_i.extend(all_pos_coef)
        # in order to turn the "sum of weights is 1" equability constrain to
        # inequality constrain, replace the original equality constrain with
        # 2 new inequality that represent a very tiny range around the original
        # right hand side of the equability constrain
        # P1 + P2 + P3 + .... > 1 - 0.0000000001
        # P1 + P2 + P3 + .... < 1 + 0.0000000001
        coefficients_for_p_i.append(sum_p_coef * -1)
        coefficients_for_p_i.append(sum_p_coef)
        coefficients_for_p_i.append(cost_coef)

        # add this list in the coefficient collection as the coefficient of
        # current variable i.e weight
        coefficients.append(coefficients_for_p_i)

        # Building objective function coefficient for this variable
        service_time = math.pow(service_rates[i], -1)
        obj_p_i_coef = \
            total_requests * (avg_data_in_per_reqs[i] +
                              avg_data_out_per_reqs[i]) * elb_prices[i] + \
            0.120 * total_requests * avg_data_out_per_reqs[i] + \
            (measurement_interval - service_time * total_requests) / \
            (service_time * measurement_interval)

        # maximise = minimise the negative form
        obj_func_coef.append(obj_p_i_coef * -1)

    """ Order Matters """
    # Now adding right hand side.
    # Right hands side has to be added in the order that coefficients was added
    # e.g in_bandwidths -> out_bandwidths -> Response time constrains -> ...
    right_hand_side.extend([in_bandwidths[n] for n in xrange(num_of_stations)])
    right_hand_side.extend([out_bandwidths[m] for m in xrange(num_of_stations)])
    right_hand_side.extend(
        [measurement_interval *
         (sla_response_t[k] - math.pow(service_rates[k], -1))
         for k in xrange(num_of_stations)]
    )
    right_hand_side.extend([0 for j in xrange(num_of_stations)])
    right_hand_side.append(0.0000000001 - 1)
    right_hand_side.append(1 + 0.0000000001)
    right_hand_side.append(budget)

    print 'coefficients: %s' % coefficients
    print 'right_hand_side: %s' % right_hand_side
    print 'obj_func_coef: %s' % obj_func_coef

    a = matrix(coefficients)
    b = matrix(right_hand_side)
    c = matrix(obj_func_coef)

    sol = solvers.lp(c, a, b)

    return sol['x']


def objective_function(variables, total_requests, data_in_per_reqs,
                       data_out_per_reqs, elb_prices,
                       m_interval, service_rates, station_latency):
    result = 0
    for i in xrange(len(variables)):
        elb_cost = \
            total_requests * (data_in_per_reqs[i] + data_out_per_reqs[i]) * \
            elb_prices[i] * variables[i]

        # we can apply accurate EC2 pricing calculation
        total_data_out = total_requests * variables[i] * data_out_per_reqs[i]
        ec2_cost = 0
        if total_data_out < 1:
            ec2_cost = 0
        elif 1 < total_data_out <= 10240:
            ec2_cost = total_data_out * 0.12
        elif 10240 < total_data_out <= 51200:
            ec2_cost = (total_data_out - 10240) * 0.09 + 10240 * 0.12
        elif 51200 < total_data_out <= 153600:
            ec2_cost = \
                (total_data_out - 51200) * 0.07 + 40960 * 0.09 + 10240 * 0.12
        elif 153600 < total_data_out <= 512000:
            ec2_cost = \
                (total_data_out - 153600) * 0.05 + 102400 * 0.07 + \
                40960 * 0.09 + 10240 * 0.12

        service_time = math.pow(service_rates[i], -1)
        total_latency = \
            service_time / \
            (1 - service_time * (total_requests * variables[i]) / m_interval) +\
            station_latency[i]

        result += elb_cost + ec2_cost + total_latency

        # Test
        # result += latency

    return result


def constrains_check(variables, total_requests,
                     data_in_per_reqs, data_out_per_reqs,
                     elb_prices, m_interval, budget,
                     in_bandwidths, out_bandwidths,service_rates,
                     station_latency):
    passes = 0  # passed constrains

    cost = 0
    for i in xrange(len(variables)):
        """ In bandwidth constrains """
        in_bandwidth = \
            total_requests * data_in_per_reqs[i] * variables[i] / m_interval

        if in_bandwidth < in_bandwidths[i]:
            passes += 1

        """ Out bandwidth constrains """
        out_bandwidth = \
            total_requests * data_out_per_reqs[i] * variables[i] / m_interval

        if out_bandwidth < out_bandwidths[i]:
            passes += 1

        """ Cost less then or equal to budget """
        elb_cost = \
            total_requests * (data_in_per_reqs[i] + data_out_per_reqs[i]) * \
            elb_prices[i] * variables[i]

        """"latency non-negative"""
        service_time = math.pow(service_rates[i], -1)
        latency = \
            service_time / \
            (1 - service_time * (total_requests * variables[i]) / m_interval) +\
            station_latency[i]

        if latency > 0:
            passes += 1

        # we can apply accurate EC2 pricing calculation
        total_data_out = total_requests * variables[i] * data_out_per_reqs[i]
        ec2_cost = 0
        if total_data_out < 1:
            ec2_cost = 0
        elif 1 < total_data_out <= 10240:
            ec2_cost = total_data_out * 0.12
        elif 10240 < total_data_out <= 51200:
            ec2_cost = (total_data_out - 10240) * 0.09 + 10240 * 0.12
        elif 51200 < total_data_out <= 153600:
            ec2_cost = \
                (total_data_out - 51200) * 0.07 + 40960 * 0.09 + 10240 * 0.12
        elif 153600 < total_data_out <= 512000:
            ec2_cost = \
                (total_data_out - 153600) * 0.05 + 102400 * 0.07 + \
                40960 * 0.09 + 10240 * 0.12

        cost += elb_cost + ec2_cost

    if cost < budget:
        passes += 1

    if passes == len(variables) * 3 + 1:
        return True

    return False


def optimisation(num_of_stations, total_requests, elb_prices,
                 avg_data_in_per_reqs, avg_data_out_per_reqs,
                 in_bandwidths, out_bandwidths, budget,
                 service_rates, measurement_interval, station_latency):
    variables = [1 for i in xrange(num_of_stations)]

    feasible_tuple = []

    # get all combination that satisfy constrains
    for i in f_range(1, 99, 0.0001):
        variables[0] = float(i) / 100.0
        variables[1] = 1 - float(i) / 100.0

        satisfy_constrains = constrains_check(variables, total_requests,
                                              avg_data_in_per_reqs,
                                              avg_data_out_per_reqs,
                                              elb_prices, measurement_interval,
                                              budget,
                                              in_bandwidths, out_bandwidths,
                                              service_rates, station_latency)
        if satisfy_constrains:
            feasible_tuple.append((variables[0], variables[1]))

    if len(feasible_tuple) == 0:
        print_message('No feasible solution found')
        return

    smallest = float("inf")
    answer = (1, 1)
    # minimisation - find the feasible tuple gives the minimal value
    for f_tuple_idx, f_tuple_val in enumerate(feasible_tuple):
        objective_result = objective_function(f_tuple_val, total_requests,
                                              avg_data_in_per_reqs,
                                              avg_data_out_per_reqs, elb_prices,
                                              measurement_interval,
                                              service_rates,
                                              station_latency)
        if objective_result < smallest:
            smallest = objective_result
            answer = f_tuple_val

    #### test ####
    total_cost = 0
    for i in xrange(len(answer)):
        elb_cost = \
            total_requests * (avg_data_in_per_reqs[i] +
                              avg_data_out_per_reqs[i]) * \
            elb_prices[i] * answer[i]

        total_data_out = total_requests * answer[i] * \
                         avg_data_out_per_reqs[i]
        ec2_cost = 0
        if total_data_out < 1:
            ec2_cost = 0
        elif 1 < total_data_out <= 10240:
            ec2_cost = total_data_out * 0.12
        elif 10240 < total_data_out <= 51200:
            ec2_cost = (total_data_out - 10240) * 0.09 + 10240 * 0.12
        elif 51200 < total_data_out <= 153600:
            ec2_cost = \
                (total_data_out - 51200) * 0.07 + 40960 * 0.09 + 10240 * 0.12
        elif 153600 < total_data_out <= 512000:
            ec2_cost = \
                (total_data_out - 153600) * 0.05 + 102400 * 0.07 + \
                40960 * 0.09 + 10240 * 0.12

        total_cost += elb_cost + ec2_cost

    print_message('')
    print_message('Total cost: $%s ' % total_cost)
    # #### test ####

    return answer