from musicxml.util.core import convert_to_xsd_class_name
from musicxml.xsd.xsdtree import XSDTree
from musicxml.xsd.xsdsimpletype import *


class XSDAttribute:
    def __init__(self, xsd_tree):
        self._xsd_tree = None
        self.xsd_tree = xsd_tree
        self._type = None
        self._is_required = None

    @property
    def xsd_tree(self):
        return self._xsd_tree

    @xsd_tree.setter
    def xsd_tree(self, value):
        if not isinstance(value, XSDTree):
            raise TypeError
        if value.tag != 'attribute':
            raise ValueError
        self._xsd_tree = value

    @property
    def name(self):
        return self.xsd_tree.get_attributes().get('name')

    @property
    def ref(self):
        return self.xsd_tree.get_attributes().get('ref')

    @property
    def type_(self):
        if self._type is None:
            self._type = eval(convert_to_xsd_class_name(self.xsd_tree.get_attributes()['type'], 'simple_type'))
        return self._type

    @property
    def is_required(self):
        if self._is_required is None:
            if self.xsd_tree.get_attributes().get('use') == 'required':
                self._is_required = True
            else:
                self._is_required = False
        return self._is_required

    def __call__(self, value):
        return self.type_(value)

    def __str__(self):
        attrs = self.xsd_tree.get_attributes()
        return f"XSDAttribute{''.join([f'@{attribute}={self.xsd_tree.get_attributes()[attribute]}' for attribute in attrs])}"

    def __repr__(self):
        return self.__str__()


