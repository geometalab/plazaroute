import logging
from flask_restplus import Resource, reqparse, fields

from plaza_routing.api.restplus import api
from plaza_routing.business.plaza_route_finder import find_route

logger = logging.getLogger('plaza_routing')
ns = api.namespace('route', description='Routing operations')

routing_arguments = reqparse.RequestParser()
routing_arguments.add_argument('start', type=str, required=True, help='Start locaton')
routing_arguments.add_argument('destination', type=str, required=True, help='Destination address')
routing_arguments.add_argument('departure', type=str, required=True, help='Departure')

WalkingRouteResponse = api.model('WalkingRouteResponse', {
    'type': fields.String(default='walking'),
    'duration': fields.Float,
    'ascend': fields.Float,
    'descend': fields.Float,
    'path': fields.List(fields.List(fields.Float))
})

PublicTransportPathResponse = api.model('PublicTransportPathResponse', {
    'name': fields.String(),
    'line_type': fields.String(),
    'line': fields.String(),
    'destination': fields.String(),
    'terminal': fields.String(),
    'departure': fields.DateTime(),
    'arrival': fields.DateTime(),
    'start_position': fields.List(fields.Float),
    'exit_position': fields.List(fields.Float)
})

PublicTransportRouteResponse = api.model('PublicTransportRouteResponse', {
    'type': fields.String(default='public_transport'),
    'duration': fields.Float,
    'number_of_legs': fields.Integer,
    'path': fields.List(fields.Nested(PublicTransportPathResponse))
})

RoutingResponse = api.model('RoutingResponse', {
    'start_walking_route': fields.Nested(WalkingRouteResponse),
    'public_transport_route': fields.Nested(PublicTransportRouteResponse),
    'end_walking_route': fields.Nested(WalkingRouteResponse),
    'accumulated_duration': fields.Float
})


@ns.route('')
class PlazaRouting(Resource):

    @ns.expect(routing_arguments)
    @api.response(200, 'Route successfully retrieved.', RoutingResponse)
    def get(self):
        args = routing_arguments.parse_args()
        start = args.get('start')
        destination = args.get('destination')
        departure = args.get('departure')
        logger.debug("Calling route() with start='%s', destination='%s', departure='%s'",
                     start, destination, departure)
        return find_route(start, destination, departure)
