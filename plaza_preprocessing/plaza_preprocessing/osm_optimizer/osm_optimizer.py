from plaza_preprocessing import osm_importer as importer
from plaza_preprocessing.osm_merger import geojson_writer
from plaza_preprocessing.osm_optimizer import helpers
from math import ceil
from shapely.geometry import (Point, MultiPoint, LineString, MultiLineString,
                              MultiPolygon, box)


class PlazaPreprocessor:

    def __init__(self, osm_id, plaza_geometry, osm_holder, graph_processor):
        self.osm_id = osm_id
        self.plaza_geometry = plaza_geometry
        self.lines = osm_holder.lines
        self.buildings = osm_holder.buildings
        self.points = osm_holder.points
        self.graph_processor = graph_processor

    def process_plaza(self):
        """ process a single plaza """
        entry_points = self._calc_entry_points()
        if len(entry_points) < 2:
            print(f"Plaza {self.osm_id} has fewer than 2 entry points")
            return
        geojson_writer.write_geojson(entry_points, 'entry_points.geojson')
        self._insert_obstacles()
        geojson_writer.write_geojson([self.plaza_geometry], 'plaza.geojson')

        self.graph_processor.entry_points = entry_points
        self.graph_processor.plaza_geometry = self.plaza_geometry
        self.graph_processor.create_graph_edges()
        geojson_writer.write_geojson(self.graph_processor.graph_edges, 'edges.geojson')

    def _calc_entry_points(self):
        """
        calculate points where lines intersect with the outer ring of the plaza
        """
        intersecting_lines = self._find_intersescting_lines()

        entry_points = []
        for line in intersecting_lines:
            intersection = line.intersection(self.plaza_geometry)
            intersection_type = type(intersection)
            if intersection_type == Point:
                entry_points.append(intersection)
            elif intersection_type == MultiPoint:
                entry_points.extend(list(intersection))
            else:
                intersection_coords = []
                if intersection_type == MultiLineString:
                    intersection_coords.extend(
                        [c for line in intersection for c in line.coords])
                else:
                    intersection_coords = list(intersection.coords)
                intersection_points = list(map(Point, intersection_coords))
                entry_points.extend(
                    [p for p in intersection_points if self.plaza_geometry.touches(p)])

        return entry_points

    def _find_intersescting_lines(self):
        """ return every line that intersects with the plaza """
        # filtering is slower than checking every line
        # bbox_buffer = 5 * 10**-3  # about 500m
        # lines_in_approx = list(
        #     filter(lambda l: line_in_plaza_approx(l, plaza_geometry, buffer=bbox_buffer), lines))
        return list(filter(self.plaza_geometry.intersects, self.lines))

    def _insert_obstacles(self):
        """ cuts out holes for obstacles on the plaza geometry """
        intersecting_buildings = self._find_intersecting_buildings()

        for building in intersecting_buildings:
            self.plaza_geometry = self.plaza_geometry.difference(building)

        points_on_plaza = self._get_points_inside_plaza()
        point_obstacles = list(
            map(lambda p: self._create_point_obstacle(p, buffer=2), points_on_plaza))

        for p_obstacle in point_obstacles:
            self.plaza_geometry = self.plaza_geometry.difference(p_obstacle)

        if isinstance(self.plaza_geometry, MultiPolygon):
            print("Multipolygon after cut out!")
            # take the largest of the polygons
            self.plaza_geometry = max(
                self.plaza_geometry, key=lambda p: p.area)

    def _find_intersecting_buildings(self):
        """ finds all buildings on the plaza that have not been cut out"""
        return list(filter(self.plaza_geometry.intersects, self.buildings))

    def _get_points_inside_plaza(self):
        """ finds all points that are on the plaza geometry """
        return list(filter(self.plaza_geometry.intersects, self.points))

    def _create_point_obstacle(self, point, buffer=5):
        """ create a polygon around a point with a buffer in meters """
        buffer_deg = helpers.meters_to_degrees(buffer)
        min_x = point.x - buffer_deg
        min_y = point.y - buffer_deg
        max_x = point.x + buffer_deg
        max_y = point.y + buffer_deg
        return box(min_x, min_y, max_x, max_y)

    def _line_in_plaza_approx(self, line, plaza_geometry, buffer=0):
        """
        determines if a line's bounding box is in the bounding box of the plaza,
        with optional buffer in degrees (enlarged bounding box)
        """
        min_x1, min_y1, max_x1, max_y1 = plaza_geometry.bounds
        line_bbox = line.bounds
        min_x1 -= buffer / 2
        min_y1 -= buffer / 2
        max_x1 += buffer / 2
        max_y1 += buffer / 2
        return helpers.bounding_boxes_overlap(min_x1, min_y1, max_x1, max_y1, *line_bbox)

    def _point_in_plaza_bbox(self, point, plaza_geometry):
        """ determines whether a point is inside the bounding box of the plaza """
        min_x, min_y, max_x, max_y = plaza_geometry.bounds
        return helpers.point_in_bounding_box(point, min_x, min_y, max_x, max_y)


class VisibilityGraphProcessor:
    def __init__(self):
        self.plaza_geometry = None
        self.entry_points = []
        self.graph_edges = []

    def create_graph_edges(self):
        """ create a visibility graph with all plaza and entry points """
        if not self.plaza_geometry:
            raise "Plaza geometry not defined for visibility graph processor"
        if not self.entry_points:
            raise "No entry points defined for graph processor"

        plaza_coords = helpers.get_polygon_coords(self.plaza_geometry)
        entry_coords = [(p.x, p.y) for p in self.entry_points]
        all_coords = set().union(plaza_coords, entry_coords)
        indexed_coords = {i: coords for i, coords in enumerate(all_coords)}
        for start_id, start_coords in indexed_coords.items():
            for end_id, end_coords in indexed_coords.items():
                if (start_id > end_id):
                    line = LineString([start_coords, end_coords])
                    if self._line_visible(line):
                        self.graph_edges.append(line)

    def _line_visible(self, line):
        """ check if the line is "visible", i.e. unobstructed through the plaza """
        return line.equals(self.plaza_geometry.intersection(line))


class SpiderWebGraphProcessor:
    def __init__(self, spacing_m):
        self.spacing_m = spacing_m
        self.plaza_geometry = None
        self.entry_points = []
        self.graph_edges = []

    def create_graph_edges(self):
        """ create a spiderwebgraph and connect edges to entry points """
        if not self.plaza_geometry:
            raise "Plaza geometry not defined for spiderwebgraph processor"
        if not self.entry_points:
            raise "No entry points defined for spiderwebgraph processor"
        self._calc_spiderwebgraph()
        self._connect_entry_points_with_graph()

    def _calc_spiderwebgraph(self):
        """ calculate spider web graph edges"""
        spacing = helpers.meters_to_degrees(self.spacing_m)
        x_left, y_bottom, x_right, y_top = self.plaza_geometry.bounds

        # based on https://github.com/michaelminn/mmqgis
        rows = int(ceil((y_top - y_bottom) / spacing))
        columns = int(ceil((x_right - x_left) / spacing))

        for column in range(0, columns + 1):
            for row in range(0, rows + 1):

                x_1 = x_left + (column * spacing)
                x_2 = x_left + ((column + 1) * spacing)
                y_1 = y_bottom + (row * spacing)
                y_2 = y_bottom + ((row + 1) * spacing)

                top_left = (x_1, y_1)
                top_right = (x_2, y_1)
                bottom_left = (x_1, y_2)
                bottom_right = (x_2, y_2)

                # horizontal line
                if column < columns:
                    h_line = self._get_spiderweb_intersection_line(top_left, top_right)
                    if h_line:
                        self.graph_edges.append(h_line)

                # vertical line
                if row < rows:
                    v_line = self._get_spiderweb_intersection_line(top_left, bottom_left)
                    if v_line:
                        self.graph_edges.append(v_line)

                # diagonal line
                if row < rows and column < columns:  # TODO correct constraint?
                    d1_line = self._get_spiderweb_intersection_line(top_left, bottom_right)
                    if d1_line:
                        self.graph_edges.append(d1_line)
                    d2_line = self._get_spiderweb_intersection_line(bottom_left, top_right)
                    if d2_line:
                        self.graph_edges.append(d2_line)

    def _get_spiderweb_intersection_line(self, start, end):
        """ returns a line that is completely inside the plaza, if possible """
        line = LineString([start, end])
        # if not line_visible(line, plaza_geometry):
        if not self.plaza_geometry.intersects(line):
            return None
        intersection = self.plaza_geometry.intersection(line)
        return intersection if isinstance(intersection, LineString) else None

    def _connect_entry_points_with_graph(self):
        print('connecting entry points')
        connection_lines = []
        for entry_point in self.entry_points:
            neighbor_line = helpers.find_nearest_geometry(entry_point, self.graph_edges)

            target_point = min(
                neighbor_line.coords, key=lambda c: Point(c).distance(entry_point))
            connection_line = (LineString([(entry_point.x, entry_point.y), target_point]))
            connection_lines.append(connection_line)
        self.graph_edges.extend(connection_lines)


def preprocess_plazas(osm_holder):
    """ preprocess all plazas from osm_importer """
    # test for helvetiaplatz
    # plaza = next(p for p in osm_holder.plazas if p['osm_id'] == 4533221)
    # test for Bahnhofplatz Bern
    # plaza = next(p for p in osm_holder.plazas if p['osm_id'] == 5117701)

    # processor = PlazaPreprocessor(
    #     plaza['osm_id'], plaza['geometry'], osm_holder, SpiderWebGraphProcessor(spacing_m=1))
    # processor.process_plaza()

    for plaza in osm_holder.plazas:
        print(f"processing plaza {plaza['osm_id']}")
        if isinstance(plaza['geometry'], MultiPolygon):
            for polygon in plaza['geometry']:
                processor = PlazaPreprocessor(
                    plaza['osm_id'], polygon, osm_holder, SpiderWebGraphProcessor(spacing_m=2))
                processor.process_plaza()

        else:
            processor = PlazaPreprocessor(
                plaza['osm_id'], plaza, osm_holder, SpiderWebGraphProcessor(spacing_m=2))
            processor.process_plaza()


if __name__ == '__main__':
    # holder = importer.import_osm('data/helvetiaplatz_umfeld.osm')
    # holder = importer.import_osm('data/switzerland-exact.osm.pbf')
    holder = importer.import_osm('data/stadt-zuerich.pbf')
    preprocess_plazas(holder)
