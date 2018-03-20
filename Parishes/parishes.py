# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Parishes
                                 A QGIS plugin
 Generate parish borders based on address ranges
                              -------------------
        begin                : 2017-09-19
        git sha              : $Format:%H$
        copyright            : (C) 2017 by Vic Mortelmans
        email                : vicmortelmans@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QVariant
from PyQt4.QtGui import QAction, QIcon
from qgis.core import QgsMapLayer, QgsExpression, QgsFeatureRequest, QgsField, QgsVectorLayer, QgsMapLayerRegistry
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from parishes_dialog import ParishesDialog
import os.path
import re
import sys
import csv
import datetime
from tqdm import tqdm
import processing


class Parishes:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Parishes_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)


        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Parishes')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'Parishes')
        self.toolbar.setObjectName(u'Parishes')

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Parishes', message)


    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        # Create the dialog (after translation) and keep reference
        self.dlg = ParishesDialog()

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/Parishes/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Parishes'),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Parishes'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def is_odd(self, number):
        if int(number) % 2 == 0:
            return False
        else:
            return True


    def write_list_of_lists_to_csv(self, list_of_lists):
        with open("errors-{:%Y%m%d-%H%M%S}.csv".format(datetime.datetime.now()), "wb") as file:
            writer = csv.writer(file)
            for list in list_of_lists:
                list = [s.encode('utf-8') if isinstance(s, basestring) else str(s).encode('utf-8') for s in list]
                writer.writerows([list])
        return


    def get_matching_ranges_request(self, city, street, parishes_table):
        # this function returns the request, not the actual ranges, because the caller wants to loop through the
        # iterator more than once
        levenshtein = 0
        while True:
            exp_string = u"levenshtein(lower(gemeente), lower('{}')) <= {} AND levenshtein(lower(straat), lower('{}')) <= {}".format(city.replace("'", r"\'"), levenshtein, street.replace("'", r"\'"), levenshtein)
            exp = QgsExpression(exp_string)
            request = QgsFeatureRequest(exp)
            ranges = parishes_table.getFeatures(request)
            range_city_street = ''
            empty = True
            unique = True
            for range in ranges:  # /!\ fetching the last element will close the iterator, even rewind() won't work
                empty = False
                if not range_city_street:
                    range_city_street = range['gemeente'] + ' ' + range['straat']
                unique = range_city_street == range['gemeente'] + ' ' + range['straat']
                if not unique:
                    break
            if not empty and unique:
                # re-create the iterator, as it has been closed by looping through it
                return request
            if not empty and not unique:
                return None
            if levenshtein > 5:
                # something's definitely wrong
                return None
            if empty:
                levenshtein += 1


    def get_addresses(self, city_street, address_layer):
        exp = QgsExpression(u"city_strt = '{}' AND APPTNR IS NULL".format(city_street.replace("'", r"\'")))
        # addresses with appartments have multiple entities, but it looks like there's always one with
        # no APPTNR value
        request = QgsFeatureRequest(exp)
        addresses = address_layer.getFeatures(request)
        return addresses


    def get_number_as_float(self, address):
        # when a number has a letter suffix, e.g. 34A, it is returned as a decimal number where the decimal is the
        # position of the letter in the alphabet, e.g. 34.01
        number_string = address['HUISNR']
        m = re.search("([0-9]+)(self[a-zA-Z]+)?", number_string)
        number = float(m.group(1))
        addendum = m.group(2)
        if addendum:
            addendum = ord(addendum.lower()) - 96
        else:
            addendum = 0
        number = number + addendum / 100
        return number


    def address_in_range(self, address, range):
        MAX = 9999
        number = self.get_number_as_float(address)
        odd_min = range['odd-min']
        odd_max = range['odd-max']
        even_min = range['even-min']
        even_max = range['even-max']
        if not odd_min:
            odd_min = 0.0
            if not odd_max:
                odd_max = MAX
        else:
            odd_min = float(odd_min)
        if not even_min:
            even_min = 0.0
            if not even_max:
                even_max = MAX
        else:
            even_min = float(even_min)
        if odd_max == 'ev':
            odd_max = MAX
        else:
            odd_max = float(odd_max)
        if even_max == 'ev':
            even_max = MAX
        else:
            even_max = float(even_max)
        if (self.is_odd(number) and odd_min <= number and number <= odd_max) or (not self.is_odd(number) and even_min <= number and number <= even_max):
            return True
        else:
            return False


    def error_range(self, range):
        return u"odd {}-{} even {}-{}".format(range['odd-min'], range['odd-max'], range['even-min'], range['even-max'])


    def assign_parish_to_addresses(self, address_layer, parishes_table):

        errors = [['city', 'street', 'number', 'error', 'range']]

        print "Start editing"
        address_layer.startEditing()

        address_fields = address_layer.fields()
        address_field_names = [field.name() for field in address_fields]
        # add fields for parish and gemeente_straatnm if needed
        if not 'parish' in address_field_names:
            print "Add field 'parish'"
            address_layer.dataProvider().addAttributes([QgsField("parish", QVariant.String)])
            address_layer.updateFields()
        if not 'city_strt' in address_field_names:
            print "Add field 'city_strt'"
            address_layer.dataProvider().addAttributes([QgsField("city_strt", QVariant.String)])
            address_layer.updateFields()

        # fill in the field city_street
        all_addresses = address_layer.getFeatures()
        print "Fill in 'city_strt'"
        for address in tqdm(all_addresses):
            address['city_strt'] = address['GEMEENTE'] + "_" + address['STRAATNM']
            address_layer.updateFeature(address)
        address_layer.commitChanges()

        # get a list of unique values for city_street
        idx = address_layer.fieldNameIndex('city_strt')
        unique_city_street_values = address_layer.uniqueValues(idx)

        # iterate per group of city_street
        address_layer.startEditing()
        print "Starting iteration streets"
        for city_street in tqdm(unique_city_street_values):
            addresses = self.get_addresses(city_street, address_layer)
            city, street = city_street.split('_', 1)
            request = self.get_matching_ranges_request(city, street, parishes_table)
            for address in addresses:
                number = self.get_number_as_float(address)
                parish = ''
                any_ranges = False
                multiple_ranges_match = False
                if request:
                    ranges = parishes_table.getFeatures(request)
                    for range in ranges:
                        any_ranges = True
                        if self.address_in_range(address, range):
                            if parish:
                                multiple_ranges_match = True
                                break
                            else:
                                parish = range['parochie']
                if not any_ranges:
                    error = [city, street, number, 'No ranges found', '']
                    errors.append(error)
                    address['parish'] = 'NO_RANGES_FOUND'
                elif multiple_ranges_match:
                    error = [city, street, number, 'Multiple ranges found', self.error_range(range)]
                    errors.append(error)
                    address['parish'] = 'MULTIPLE_RANGES_APPLY'
                elif not parish:
                    error = [city, street, number, 'No ranges apply', self.error_range(range)]
                    errors.append(error)
                    address['parish'] = 'NO_RANGE_APPLIES'
                else:
                    # success!
                    address['parish'] = parish
                address_layer.updateFeature(address)
        result = address_layer.commitChanges()
        if result:
            print "Done editing"
        else:
            print "Done editing, but commit failed!"
        self.write_list_of_lists_to_csv(errors)


    def run(self):
        """Run method that performs all the real work"""
        import pydevd
        pydevd.settrace('localhost', port=53100, stdoutToServer=True, stderrToServer=True)
        layers = self.iface.legendInterface().layers()
        layer_dict_vector = {}
        layer_dict_table = {}
        for layer in layers:
            if layer.type() == QgsMapLayer.VectorLayer:
                if layer.isSpatial():
                    layer_dict_vector[layer.name()] = layer
                else:
                    layer_dict_table[layer.name()] = layer
        self.dlg.comboBox_vector.addItems(layer_dict_vector.keys())
        self.dlg.comboBox_table.addItems(layer_dict_table.keys())
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            layer_name_vector = self.dlg.comboBox_vector.currentText()
            layer_name_table = self.dlg.comboBox_table.currentText()
            layer_vector = layer_dict_vector[layer_name_vector]
            layer_table = layer_dict_table[layer_name_table]
            print "Number of addresses in vector layer: {}".format(layer_vector.featureCount())
            self.assign_parish_to_addresses(layer_vector, layer_table)
            # Select the features with valid parish field (parish ~ '^[^_]+$')
            layer_vector.selectByExpression("parish ~ '^[^_]+$'", QgsVectorLayer.SetSelection)
            print "Number of addresses in vector layer with valid parish assignment: {}".format(layer_vector.selectedFeatureCount())
            # Create a memory layer for storing the selected features
            selected_features = layer_vector.selectedFeatures()  # TODO here may be a chance to limit the number of attributes
            layer_attributes = layer_vector.dataProvider().fields().toList()
            layer_selected = QgsVectorLayer("Point", "Layer_Selected", "memory")  # TODO may need to provide CRS after Point
            layer_selected.dataProvider().addAttributes(layer_attributes)
            layer_selected.updateFields()
            layer_selected.dataProvider().addFeatures(selected_features)
            QgsMapLayerRegistry.instance().addMapLayer(layer_selected)
            print "Valid addresses copied to memory layer OK"
            # Get the extent of the selected features as input for further processing
            extent = layer_selected.extent()
            xmin = extent.xMinimum()
            xmax = extent.xMaximum()
            ymin = extent.yMinimum()
            ymax = extent.yMaximum()
            extent_parameter = "%f,%f,%f,%f" % (xmin, xmax, ymin, ymax)
            # Create the voronoi polygons
            layer_voronoi = processing.runalg("grass:v.voronoi", layer_selected, False, False, extent_parameter, -1, 0.0001, 0, None)
            print "Voronoi polygons OK"
            pass


