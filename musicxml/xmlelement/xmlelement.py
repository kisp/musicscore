import copy
import xml.etree.ElementTree as ET
from typing import Optional, List, Callable, Union

from musicxml.exceptions import XSDWrongAttribute, XSDAttributeRequiredException, XMLElementChildrenRequired
from musicxml.generate_classes.utils import musicxml_xsd_et_root, ns
from tree.tree import Tree
from musicxml.util.core import cap_first, replace_key_underline_with_hyphen
from musicxml.xmlelement.containers import containers
from musicxml.xmlelement.exceptions import XMLElementCannotHaveChildrenError
from musicxml.xmlelement.xmlchildcontainer import DuplicationXSDSequence
from musicxml.xsd.xsdcomplextype import *
from musicxml.xsd.xsdsimpletype import *
from musicxml.xsd.xsdtree import XSDTree


class XMLElement(Tree):
    PROPERTIES = {'compact_repr', 'is_leaf', 'level', 'attributes', 'child_container_tree', 'possible_children_names',
                  'et_xml_element', 'name', 'type_', 'value_', 'parent_xsd_element'}
    TYPE = None
    XSD_TREE: Optional[XSDTree] = None

    def __init__(self, value_=None, **kwargs):
        self._type = None
        super().__init__()
        self._value_ = None
        self._attributes = {}
        self._et_xml_element = None
        self._child_container_tree = None
        self._unordered_children = []
        self.value_ = value_
        self._set_attributes(kwargs)

        self._create_child_container_tree()

    def _check_attribute(self, name, value):
        attributes = self.TYPE.get_xsd_attributes()
        allowed_attributes = [attribute.name for attribute in attributes]
        if name not in [attribute.name for attribute in self.TYPE.get_xsd_attributes()]:
            raise XSDWrongAttribute(f"{self.__class__.__name__} has no attribute {name}. Allowed attributes are: {allowed_attributes}")
        for attribute in attributes:
            if attribute.name == name:
                return attribute(value)

    def _check_child_to_be_added(self, child):
        if not isinstance(child, XMLElement):
            raise TypeError

    def _check_required_attributes(self):
        if self.TYPE.XSD_TREE.is_complex_type:
            required_attributes = [attribute for attribute in self.TYPE.get_xsd_attributes() if attribute.is_required]
            for required_attribute in required_attributes:
                if required_attribute.name not in self.attributes:
                    raise XSDAttributeRequiredException(f"{self.__class__.__name__} requires attribute: {required_attribute.name}")

    def _check_required_value(self):
        if self.TYPE.XSD_TREE.is_simple_type and self.value_ is None:
            raise ValueError(f"{self.__class__.__name__} needs a value.")

    def _convert_attribute_to_child(self, name, value):
        if not name.startswith('xml_'):
            raise NameError
        child_name = name.replace('xml_', '')

        if '-'.join(child_name.split('_')) not in self.possible_children_names:
            raise NameError

        child_class_name = 'XML' + ''.join([cap_first(partial) for partial in child_name.split('_')])
        child_class = eval(child_class_name)

        found_child = self.find_child(child_class_name)
        if isinstance(value, child_class):
            if found_child:
                self.replace_child(found_child, value)
            else:
                self.add_child(value)
        elif value is None:
            if found_child:
                self.remove(found_child)
        else:
            if found_child:
                found_child.value_ = value
            else:
                self.add_child(child_class(value))

    def _create_child_container_tree(self):
        try:
            if self.TYPE.XSD_TREE.is_complex_type:
                self._child_container_tree = copy.copy(containers[self.TYPE.__name__])
                self._child_container_tree._parent_xml_element = self
        except KeyError:
            pass

    def _create_et_xml_element(self):
        self._et_xml_element = ET.Element(self.name, {k: str(v) for k, v in self.attributes.items()})
        if self.value_ is not None:
            self._et_xml_element.text = str(self.value_)
        for child in self.get_children():
            self._et_xml_element.append(child.et_xml_element)
        ET.indent(self._et_xml_element, space="  ", level=self.level)

    def _final_checks(self, intelligent_choice=False):
        self._check_required_value()
        if self._child_container_tree:
            required_children = self._child_container_tree.get_required_element_names(intelligent_choice=intelligent_choice)
            if required_children:
                raise XMLElementChildrenRequired(f"{self.__class__.__name__} requires at least following children: {required_children}")

        self._check_required_attributes()

        for child in self.get_children():
            child._final_checks(intelligent_choice=intelligent_choice)

    def _get_attributes_error_message(self, wrong_name):
        attributes = self.TYPE.get_xsd_attributes()
        allowed_attributes = [attribute.name for attribute in attributes]
        return f"{self.__class__.__name__} has no attribute {wrong_name}. Allowed attributes are: " \
               f"{sorted(allowed_attributes)} or possible " \
               f"children as attributes: {sorted(['xml_' + '_'.join(ch.split('-')) for ch in self.possible_children_names])}"

    def _set_attributes(self, val):
        if val is None:
            return

        if self.TYPE.XSD_TREE.is_simple_type:
            if val:
                raise XSDWrongAttribute(f'{self.__class__.__name__} has no attributes.')

        elif not isinstance(val, dict):
            raise TypeError

        new_attributes = replace_key_underline_with_hyphen(dict_=val)
        none_values_dict = {k: v for k, v in new_attributes.items() if v is None}
        for key in none_values_dict:
            new_attributes.pop(key)
            try:
                self.attributes.pop(key)
            except KeyError:
                pass
        for key in new_attributes:
            self._check_attribute(key, new_attributes[key])
        self._attributes = {**self._attributes, **new_attributes}

    @property
    def attributes(self):
        """
        :return: a dictionary of attributes like {'font-family': 'Arial'} if XMLElement.font_family is set to Arial. The attributes will
        appear in the main xml tag: <text font-family="Arial">hello</text>.
        """
        return self._attributes

    @property
    def child_container_tree(self):
        """
        :return: A ChildContainerTree object which is used to manage and control XMLElements children. The nodes of a ChildContainerTree
        have a core content property of types XSDSequence, XSDChoice, XSDGroup or XSDElement. XSDElement are the content type of
        ChildContainerTree leaves where one or more XMLElements of a single type (depending on maxOccur attribute of element) can be
        added to its xml_elements list. An interaction of xsd indicators (sequence, choice and group) with xsd elements makes it possible to
        add XMLElement's Children in the right order and control all xsd rules which apply to musicxml. A variety of exceptions help user to
        control the xml structure of the exported file which they are intending to use as a musicxml format file.
        """
        return self._child_container_tree

    @property
    def et_xml_element(self):
        """
        :return:  A xml.etree.ElementTree.Element which is used to write the musicxml file.
        """
        self._create_et_xml_element()
        return self._et_xml_element

    @property
    def name(self):
        return self.XSD_TREE.get_attributes()['name']

    @property
    def possible_children_names(self):
        if not self.child_container_tree:
            return {}
        else:
            return {leaf.content.name for leaf in self.child_container_tree.iterate_leaves()}

    @property
    def value_(self):
        """
        :return: A validated value of XMLElement which will be translated to its text in xml format.
        """
        return self._value

    @value_.setter
    def value_(self, val):
        """
        :param val: Value to be validated and added to XMLElement. This value will be translated to xml element's text in xml format.
        """
        self.TYPE(val, parent=self)
        self._value = val

    @classmethod
    def get_xsd(cls):
        """
        :return: Snippet of musicxml xsd file which is relevant for this XMLElement.
        """
        return cls.XSD_TREE.get_xsd()

    def add_child(self, child: 'XMLElement', forward: Optional[int] = None) -> 'XMLElement':
        """
        :param XMLElement child: XMLElement child to be added to XMLElement's ChildContainerTree and _unordered_children.
        :param int forward: If there are more than one XSDElement leaves in self.child_container_tree, forward can be used to determine
        manually which of these equivocal xsd elements is going to be used to attach the child.
        :return: Added child.
        """
        if not self._child_container_tree:
            raise XMLElementCannotHaveChildrenError()
        self._child_container_tree.add_element(child, forward)
        self._unordered_children.append(child)
        child._parent = self
        return child

    def get_children(self, ordered: bool = True) -> List['XMLElement']:
        """
        :param bool ordered: True or False.
        :return: XMLElement added children. If ordered is False the _unordered_children is returned as a more light weighted way of
        getting children instead of using the leaves of ChildContainerTree.
        """
        if ordered is False:
            return self._unordered_children
        if self._child_container_tree:
            return [xml_element for leaf in self._child_container_tree.iterate_leaves() for xml_element in leaf.content.xml_elements if
                    leaf.content.xml_elements]
        else:
            return []

    def find_child(self, name: Union['XMLElement', str], ordered: bool = False) -> 'XMLElement':
        """
        :param XMLElement/String name: Child or it's name as string.
        :param bool ordered: get_children mode to be used to find first appearance of child.
        :return: found child.
        """
        if isinstance(name, type):
            name = name.__name__
        for ch in self.get_children(ordered=ordered):
            if ch.__class__.__name__ == name:
                return ch

    def find_children(self, name: Union['XMLElement', str], ordered: bool = False) -> List['XMLElement']:
        """
        :param XMLElement/String name: Child or it's name as string.
        :param bool ordered: get_children mode to be used to find children.
        :return: found children.
        """
        if isinstance(name, type):
            name = name.__name__
        return [ch for ch in self.get_children(ordered=ordered) if ch.__class__.__name__ == name]

    def remove(self, child: 'XMLElement') -> None:
        """
        :param XMLElement child: child to be removed. This method must be used to remove a child properly from ChildContainerTree and
        reset its behaviour.
        :return: None
        """

        def remove_duplictation():
            for node in parent_container.reversed_path_to_root():
                if node.up:
                    if isinstance(node.up.content, DuplicationXSDSequence) and len(node.up.get_children()) > 1:
                        remove_duplicate = False
                        for leaf in node.iterate_leaves():
                            if leaf != parent_container and leaf.content.xml_elements:
                                break
                            remove_duplicate = True
                        if remove_duplicate:
                            node.up.remove(node)

        self._unordered_children.remove(child)

        parent_container = child.parent_xsd_element.parent_container.get_parent()
        if parent_container.chosen_child == child.parent_xsd_element.parent_container:
            parent_container.chosen_child = None
            parent_container.requirements_not_fulfilled = True

        child.parent_xsd_element.xml_elements.remove(child)
        child.parent_xsd_element = None
        child._parent = None
        del child
        remove_duplictation()

    def replace_child(self, old: Union['XMLElement', Callable], new: 'XMLElement', index: int = 0) -> None:
        """
        :param XMLElement or function old: A child or function which is used to find a child to be replaced.
        :param XMLElement new: child to be replaced with.
        :param int index: index of old in list of old appearances
        :return: None
        """
        if hasattr(old, '__call__'):
            list_of_olds = [ch for ch in self.get_children(ordered=True) if old(ch)]
        else:
            list_of_olds = [ch for ch in self.get_children(ordered=True) if ch == old]

        if not list_of_olds:
            raise ValueError(f"{old} not in list.")
        self._check_child_to_be_added(new)
        old_index = self._unordered_children.index(list_of_olds[index])
        old_child = self._unordered_children[old_index]
        self._unordered_children.remove(old_child)
        self._unordered_children.insert(old_index, new)

        parent_xsd_element = old_child.parent_xsd_element
        new.parent_xsd_element = parent_xsd_element
        parent_xsd_element._xml_elements = [new if el == old_child else el for el in parent_xsd_element.xml_elements]
        new._parent = self
        old._parent = None

    def to_string(self, intelligent_choice: bool = False) -> str:
        """
        :param bool intelligent_choice: Set to True if you wish to use intelligent choice in final checks to be able to change the
        attachment order of XMLElement children in self.child_container_tree if an Exception was thrown and other choices can still be
        checked. (No GUARANTEE!)
        :return: String in xml format.
        """
        self._final_checks(intelligent_choice=intelligent_choice)
        self._create_et_xml_element()

        return ET.tostring(self.et_xml_element, encoding='unicode') + '\n'

    def __setattr__(self, key, value):
        if key[0] == '_' or key in self.PROPERTIES:
            super().__setattr__(key, value)
        elif key.startswith('xml_'):
            try:
                self._convert_attribute_to_child(name=key, value=value)
            except NameError:
                raise AttributeError(self._get_attributes_error_message(key))
        else:
            try:
                self._set_attributes({key: value})
            except XSDWrongAttribute:
                raise AttributeError(self._get_attributes_error_message(key))

    def __getattr__(self, item):
        try:
            return self.attributes['-'.join(item.split('_'))]
        except KeyError:
            attributes = self.TYPE.get_xsd_attributes()
            allowed_attributes = ['_'.join(attribute.name.split('-')) for attribute in attributes]
            if item in allowed_attributes:
                return None
            else:
                if item.startswith('xml'):
                    child_name = item.replace('xml_', '')
                    for child in self.get_children(ordered=False):
                        if child.name == '-'.join(child_name.split('_')):
                            return child
                    if '-'.join(child_name.split('_')) in self.possible_children_names:
                        return None
                raise AttributeError(self._get_attributes_error_message(item))


# xml score partwise
xsd_tree_score_partwise_part = XSDTree(musicxml_xsd_et_root.find(f".//{ns}element[@name='score-partwise']"))
"""
<xs:element name="score-partwise" block="extension substitution" final="#all">
    <xs:annotation>
        <xs:documentation>The score-partwise element is the root element for a partwise MusicXML score. It includes a score-header group followed by a series of parts with measures inside. The document-attributes attribute group includes the version attribute.</xs:documentation>
    </xs:annotation>
    <xs:complexType>
        <xs:sequence>
            <xs:group ref="score-header"/>
            <xs:element name="part" maxOccurs="unbounded">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="measure" maxOccurs="unbounded">
                            <xs:complexType>
                                <xs:group ref="music-data"/>
                                <xs:attributeGroup ref="measure-attributes"/>
                            </xs:complexType>
                        </xs:element>
                    </xs:sequence>
                    <xs:attributeGroup ref="part-attributes"/>
                </xs:complexType>
            </xs:element>
        </xs:sequence>
        <xs:attributeGroup ref="document-attributes"/>
    </xs:complexType>
</xs:element>
"""


class XMLScorePartwise(XMLElement):
    TYPE = XSDComplexTypeScorePartwise
    XSD_TREE = XSDTree(musicxml_xsd_et_root.find(f".//{ns}element[@name='score-partwise']"))

    def write(self, path, intelligent_choice=False):
        with open(path, 'w') as file:
            file.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
            file.write(self.to_string(intelligent_choice=intelligent_choice))

    @property
    def __doc__(self):
        return self.XSD_TREE.get_doc()


class XMLPart(XMLElement):
    TYPE = XSDComplexTypePart
    XSD_TREE = XSDTree(musicxml_xsd_et_root.findall(f".//{ns}element[@name='score-partwise']//{ns}element")[0])

    @property
    def __doc__(self):
        return self.XSD_TREE.get_doc()


class XMLMeasure(XMLElement):
    TYPE = XSDComplexTypeMeasure
    XSD_TREE = XSDTree(musicxml_xsd_et_root.findall(f".//{ns}element[@name='score-partwise']//{ns}element")[1])

    @property
    def __doc__(self):
        return self.XSD_TREE.get_doc()


class XMLDirective(XMLElement):
    TYPE = XSDComplexTypeDirective
    XSD_TREE = XSDTree(musicxml_xsd_et_root.find(".//{*}complexType[@name='attributes']//{*}element[@name='directive']"))

    @property
    def __doc__(self):
        return self.XSD_TREE.get_doc()
# -----------------------------------------------------
# AUTOMATICALLY GENERATED WITH generate_xml_elements.py
# -----------------------------------------------------


class XMLP(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="p" type="empty" />
"""
                                     ))


class XMLPp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pp" type="empty" />
"""
                                     ))


class XMLPpp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ppp" type="empty" />
"""
                                     ))


class XMLPppp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pppp" type="empty" />
"""
                                     ))


class XMLPpppp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ppppp" type="empty" />
"""
                                     ))


class XMLPppppp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pppppp" type="empty" />
"""
                                     ))


class XMLF(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="f" type="empty" />
"""
                                     ))


class XMLFf(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ff" type="empty" />
"""
                                     ))


class XMLFff(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fff" type="empty" />
"""
                                     ))


class XMLFfff(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ffff" type="empty" />
"""
                                     ))


class XMLFffff(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fffff" type="empty" />
"""
                                     ))


class XMLFfffff(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ffffff" type="empty" />
"""
                                     ))


class XMLMp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="mp" type="empty" />
"""
                                     ))


class XMLMf(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="mf" type="empty" />
"""
                                     ))


class XMLSf(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sf" type="empty" />
"""
                                     ))


class XMLSfp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sfp" type="empty" />
"""
                                     ))


class XMLSfpp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sfpp" type="empty" />
"""
                                     ))


class XMLFp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fp" type="empty" />
"""
                                     ))


class XMLRf(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="rf" type="empty" />
"""
                                     ))


class XMLRfz(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="rfz" type="empty" />
"""
                                     ))


class XMLSfz(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sfz" type="empty" />
"""
                                     ))


class XMLSffz(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sffz" type="empty" />
"""
                                     ))


class XMLFz(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fz" type="empty" />
"""
                                     ))


class XMLN(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="n" type="empty" />
"""
                                     ))


class XMLPf(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pf" type="empty" />
"""
                                     ))


class XMLSfzp(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sfzp" type="empty" />
"""
                                     ))


class XMLOtherDynamics(XMLElement):
    """
    The other-text type represents a text element with a smufl attribute group. This type is used by MusicXML direction extension elements to allow specification of specific SMuFL glyphs without needed to add every glyph as a MusicXML element.
    """
    
    TYPE = XSDComplexTypeOtherText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-dynamics" type="other-text" />
"""
                                     ))


class XMLMidiChannel(XMLElement):
    """
    The midi-channel element specifies a MIDI 1.0 channel numbers ranging from 1 to 16.
    """
    
    TYPE = XSDSimpleTypeMidi16
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="midi-channel" type="midi-16" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The midi-channel element specifies a MIDI 1.0 channel numbers ranging from 1 to 16.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMidiName(XMLElement):
    """
    The midi-name element corresponds to a ProgramName meta-event within a Standard MIDI File.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="midi-name" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The midi-name element corresponds to a ProgramName meta-event within a Standard MIDI File.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMidiBank(XMLElement):
    """
    The midi-bank element specifies a MIDI 1.0 bank number ranging from 1 to 16,384.
    """
    
    TYPE = XSDSimpleTypeMidi16384
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="midi-bank" type="midi-16384" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The midi-bank element specifies a MIDI 1.0 bank number ranging from 1 to 16,384.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMidiProgram(XMLElement):
    """
    The midi-program element specifies a MIDI 1.0 program number ranging from 1 to 128.
    """
    
    TYPE = XSDSimpleTypeMidi128
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="midi-program" type="midi-128" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The midi-program element specifies a MIDI 1.0 program number ranging from 1 to 128.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMidiUnpitched(XMLElement):
    """
    For unpitched instruments, the midi-unpitched element specifies a MIDI 1.0 note number ranging from 1 to 128. It is usually used with MIDI banks for percussion. Note that MIDI 1.0 note numbers are generally specified from 0 to 127 rather than the 1 to 128 numbering used in this element.
    """
    
    TYPE = XSDSimpleTypeMidi128
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="midi-unpitched" type="midi-128" minOccurs="0">
    <xs:annotation>
        <xs:documentation>For unpitched instruments, the midi-unpitched element specifies a MIDI 1.0 note number ranging from 1 to 128. It is usually used with MIDI banks for percussion. Note that MIDI 1.0 note numbers are generally specified from 0 to 127 rather than the 1 to 128 numbering used in this element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLVolume(XMLElement):
    """
    The volume element value is a percentage of the maximum ranging from 0 to 100, with decimal values allowed. This corresponds to a scaling value for the MIDI 1.0 channel volume controller.
    """
    
    TYPE = XSDSimpleTypePercent
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="volume" type="percent" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The volume element value is a percentage of the maximum ranging from 0 to 100, with decimal values allowed. This corresponds to a scaling value for the MIDI 1.0 channel volume controller.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPan(XMLElement):
    """
    The pan and elevation elements allow placing of sound in a 3-D space relative to the listener. Both are expressed in degrees ranging from -180 to 180. For pan, 0 is straight ahead, -90 is hard left, 90 is hard right, and -180 and 180 are directly behind the listener.
    """
    
    TYPE = XSDSimpleTypeRotationDegrees
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pan" type="rotation-degrees" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The pan and elevation elements allow placing of sound in a 3-D space relative to the listener. Both are expressed in degrees ranging from -180 to 180. For pan, 0 is straight ahead, -90 is hard left, 90 is hard right, and -180 and 180 are directly behind the listener.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLElevation(XMLElement):
    """
    The elevation and pan elements allow placing of sound in a 3-D space relative to the listener. Both are expressed in degrees ranging from -180 to 180. For elevation, 0 is level with the listener, 90 is directly above, and -90 is directly below.
    """
    
    TYPE = XSDSimpleTypeRotationDegrees
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="elevation" type="rotation-degrees" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The elevation and pan elements allow placing of sound in a 3-D space relative to the listener. Both are expressed in degrees ranging from -180 to 180. For elevation, 0 is level with the listener, 90 is directly above, and -90 is directly below.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDisplayText(XMLElement):
    """
    The formatted-text type represents a text element with text-formatting attributes.
    """
    
    TYPE = XSDComplexTypeFormattedText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="display-text" type="formatted-text" />
"""
                                     ))


class XMLAccidentalText(XMLElement):
    """
    The accidental-text type represents an element with an accidental value and text-formatting attributes.
    """
    
    TYPE = XSDComplexTypeAccidentalText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accidental-text" type="accidental-text" />
"""
                                     ))


class XMLIpa(XMLElement):
    """
    The ipa element represents International Phonetic Alphabet (IPA) sounds for vocal music. String content is limited to IPA 2015 symbols represented in Unicode 13.0.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ipa" type="xs:string">
    <xs:annotation>
        <xs:documentation>The ipa element represents International Phonetic Alphabet (IPA) sounds for vocal music. String content is limited to IPA 2015 symbols represented in Unicode 13.0.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMute(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeMute
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="mute" type="mute" />
"""
                                     ))


class XMLSemiPitched(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeSemiPitched
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="semi-pitched" type="semi-pitched" />
"""
                                     ))


class XMLOtherPlay(XMLElement):
    """
    The other-play element represents other types of playback. The required type attribute indicates the type of playback to which the element content applies.
    """
    
    TYPE = XSDComplexTypeOtherPlay
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-play" type="other-play" />
"""
                                     ))


class XMLDivisions(XMLElement):
    """
    Musical notation duration is commonly represented as fractions. The divisions element indicates how many divisions per quarter note are used to indicate a note's duration. For example, if duration = 1 and divisions = 2, this is an eighth note duration. Duration and divisions are used directly for generating sound output, so they must be chosen to take tuplets into account. Using a divisions element lets us use just one number to represent a duration for each note in the score, while retaining the full power of a fractional representation. If maximum compatibility with Standard MIDI 1.0 files is important, do not have the divisions value exceed 16383.
    """
    
    TYPE = XSDSimpleTypePositiveDivisions
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="divisions" type="positive-divisions" minOccurs="0">
    <xs:annotation>
        <xs:documentation>Musical notation duration is commonly represented as fractions. The divisions element indicates how many divisions per quarter note are used to indicate a note's duration. For example, if duration = 1 and divisions = 2, this is an eighth note duration. Duration and divisions are used directly for generating sound output, so they must be chosen to take tuplets into account. Using a divisions element lets us use just one number to represent a duration for each note in the score, while retaining the full power of a fractional representation. If maximum compatibility with Standard MIDI 1.0 files is important, do not have the divisions value exceed 16383.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLKey(XMLElement):
    """
    The key type represents a key signature. Both traditional and non-traditional key signatures are supported. The optional number attribute refers to staff numbers. If absent, the key signature applies to all staves in the part. Key signatures appear at the start of each system unless the print-object attribute has been set to "no".\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Group\@name=traditional-key\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=cancel\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=fifths\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=mode\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Group\@name=non-traditional-key\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=key-step\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=key-alter\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=key-accidental\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=key-octave\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeKey
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="key" type="key" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The key element represents a key signature. Both traditional and non-traditional key signatures are supported. The optional number attribute refers to staff numbers. If absent, the key signature applies to all staves in the part.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTime(XMLElement):
    """
    Time signatures are represented by the beats element for the numerator and the beat-type element for the denominator. The symbol attribute is used to indicate common and cut time symbols as well as a single number display. Multiple pairs of beat and beat-type elements are used for composite time signatures with multiple denominators, such as 2/4 + 3/8. A composite such as 3+2/8 requires only one beat/beat-type pair.
    
    The print-object attribute allows a time signature to be specified but not printed, as is the case for excerpts from the middle of a score. The value is "yes" if not present. The optional number attribute refers to staff numbers within the part. If absent, the time signature applies to all staves in the part.\n
    XSD structure:\n
    Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Group\@name=time-signature\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=beats\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=beat-type\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=interchangeable\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=senza-misura\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeTime
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="time" type="time" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>Time signatures are represented by the beats element for the numerator and the beat-type element for the denominator.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStaves(XMLElement):
    """
    The staves element is used if there is more than one staff represented in the given part (e.g., 2 staves for typical piano parts). If absent, a value of 1 is assumed. Staves are ordered from top to bottom in a part in numerical order, with staff 1 above staff 2.
    """
    
    TYPE = XSDSimpleTypeNonNegativeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staves" type="xs:nonNegativeInteger" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The staves element is used if there is more than one staff represented in the given part (e.g., 2 staves for typical piano parts). If absent, a value of 1 is assumed. Staves are ordered from top to bottom in a part in numerical order, with staff 1 above staff 2.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPartSymbol(XMLElement):
    """
    The part-symbol type indicates how a symbol for a multi-staff part is indicated in the score; brace is the default value. The top-staff and bottom-staff attributes are used when the brace does not extend across the entire part. For example, in a 3-staff organ part, the top-staff will typically be 1 for the right hand, while the bottom-staff will typically be 2 for the left hand. Staff 3 for the pedals is usually outside the brace. By default, the presence of a part-symbol element that does not extend across the entire part also indicates a corresponding change in the common barlines within a part.
    """
    
    TYPE = XSDComplexTypePartSymbol
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-symbol" type="part-symbol" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The part-symbol element indicates how a symbol for a multi-staff part is indicated in the score.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInstruments(XMLElement):
    """
    The instruments element is only used if more than one instrument is represented in the part (e.g., oboe I and II where they play together most of the time). If absent, a value of 1 is assumed.
    """
    
    TYPE = XSDSimpleTypeNonNegativeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="instruments" type="xs:nonNegativeInteger" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The instruments element is only used if more than one instrument is represented in the part (e.g., oboe I and II where they play together most of the time). If absent, a value of 1 is assumed.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLClef(XMLElement):
    """
    Clefs are represented by a combination of sign, line, and clef-octave-change elements. The optional number attribute refers to staff numbers within the part. A value of 1 is assumed if not present.
    
    Sometimes clefs are added to the staff in non-standard line positions, either to indicate cue passages, or when there are multiple clefs present simultaneously on one staff. In this situation, the additional attribute is set to "yes" and the line value is ignored. The size attribute is used for clefs where the additional attribute is "yes". It is typically used to indicate cue clefs.
    
    Sometimes clefs at the start of a measure need to appear after the barline rather than before, as for cues or for use after a repeated section. The after-barline attribute is set to "yes" in this situation. The attribute is ignored for mid-measure clefs.
    
    Clefs appear at the start of each system unless the print-object attribute has been set to "no" or the additional attribute has been set to "yes".\n
    XSD structure:\n
    Group\@name=clef\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=sign\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=line\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=clef-octave-change\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeClef
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="clef" type="clef" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>Clefs are represented by a combination of sign, line, and clef-octave-change elements.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStaffDetails(XMLElement):
    """
    The staff-details element is used to indicate different types of staves. The optional number attribute specifies the staff number from top to bottom on the system, as with clef. The print-object attribute is used to indicate when a staff is not printed in a part, usually in large scores where empty parts are omitted. It is yes by default. If print-spacing is yes while print-object is no, the score is printed in cutaway format where vertical space is left for the empty part.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=staff-type\@minOccurs=0\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=staff-lines\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=line-detail\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=staff-tuning\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=capo\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=staff-size\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeStaffDetails
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-details" type="staff-details" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The staff-details element is used to indicate different types of staves.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTranspose(XMLElement):
    """
    The transpose type represents what must be added to a written pitch to get a correct sounding pitch. The optional number attribute refers to staff numbers, from top to bottom on the system. If absent, the transposition applies to all staves in the part. Per-staff transposition is most often used in parts that represent multiple instruments.\n
    XSD structure:\n
    Group\@name=transpose\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=diatonic\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=chromatic\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=octave-change\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=double\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeTranspose
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="transpose" type="transpose" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>If the part is being encoded for a transposing instrument in written vs. concert pitch, the transposition must be encoded in the transpose element using the transpose type.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLForPart(XMLElement):
    """
    The for-part type is used in a concert score to indicate the transposition for a transposed part created from that score. It is only used in score files that contain a concert-score element in the defaults. This allows concert scores with transposed parts to be represented in a single uncompressed MusicXML file.
    
    The optional number attribute refers to staff numbers, from top to bottom on the system. If absent, the child elements apply to all staves in the created part.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=part-clef\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=part-transpose\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeForPart
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="for-part" type="for-part" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The for-part element is used in a concert score to indicate the transposition for a transposed part created from that score. It is only used in score files that contain a concert-score element in the defaults. This allows concert scores with transposed parts to be represented in a single uncompressed MusicXML file.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMeasureStyle(XMLElement):
    """
    A measure-style indicates a special way to print partial to multiple measures within a part. This includes multiple rests over several measures, repeats of beats, single, or multiple measures, and use of slash notation.
    
    The multiple-rest and measure-repeat elements indicate the number of measures covered in the element content. The beat-repeat and slash elements can cover partial measures. All but the multiple-rest element use a type attribute to indicate starting and stopping the use of the style. The optional number attribute specifies the staff number from top to bottom on the system, as with clef.\n
    XSD structure:\n
    Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=multiple-rest\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=measure-repeat\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=beat-repeat\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=slash\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeMeasureStyle
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="measure-style" type="measure-style" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>A measure-style indicates a special way to print partial to multiple measures within a part. This includes multiple rests over several measures, repeats of beats, single, or multiple measures, and use of slash notation.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPartClef(XMLElement):
    """
    The child elements of the part-clef type have the same meaning as for the clef type. However that meaning applies to a transposed part created from the existing score file.\n
    XSD structure:\n
    Group\@name=clef\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=sign\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=line\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=clef-octave-change\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePartClef
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-clef" type="part-clef" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The part-clef element is used for transpositions that also include a change of clef, as for instruments such as bass clarinet.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPartTranspose(XMLElement):
    """
    The child elements of the part-transpose type have the same meaning as for the transpose type. However that meaning applies to a transposed part created from the existing score file.\n
    XSD structure:\n
    Group\@name=transpose\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=diatonic\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=chromatic\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=octave-change\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=double\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePartTranspose
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-transpose" type="part-transpose">
    <xs:annotation>
        <xs:documentation>The chromatic element in a part-transpose element will usually have a non-zero value, since octave transpositions can be represented in concert scores using the transpose element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTimeRelation(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTimeRelation
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="time-relation" type="time-relation" minOccurs="0" />
"""
                                     ))


class XMLKeyOctave(XMLElement):
    """
    The key-octave type specifies in which octave an element of a key signature appears. The content specifies the octave value using the same values as the display-octave element. The number attribute is a positive integer that refers to the key signature element in left-to-right order. If the cancel attribute is set to yes, then this number refers to the canceling key signature specified by the cancel element in the parent key element. The cancel attribute cannot be set to yes if there is no corresponding cancel element within the parent key element. It is no by default.
    """
    
    TYPE = XSDComplexTypeKeyOctave
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="key-octave" type="key-octave" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The optional list of key-octave elements is used to specify in which octave each element of the key signature appears.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMultipleRest(XMLElement):
    """
    The text of the multiple-rest type indicates the number of measures in the multiple rest. Multiple rests may use the 1-bar / 2-bar / 4-bar rest symbols, or a single shape. The use-symbols attribute indicates which to use; it is no if not specified.
    """
    
    TYPE = XSDComplexTypeMultipleRest
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="multiple-rest" type="multiple-rest" />
"""
                                     ))


class XMLMeasureRepeat(XMLElement):
    """
    The measure-repeat type is used for both single and multiple measure repeats. The text of the element indicates the number of measures to be repeated in a single pattern. The slashes attribute specifies the number of slashes to use in the repeat sign. It is 1 if not specified. The text of the element is ignored when the type is stop.
    
    The stop type indicates the first measure where the repeats are no longer displayed. Both the start and the stop of the measure-repeat should be specified unless the repeats are displayed through the end of the part.
    
    The measure-repeat element specifies a notation style for repetitions. The actual music being repeated needs to be repeated within each measure of the MusicXML file. This element specifies the notation that indicates the repeat.
    """
    
    TYPE = XSDComplexTypeMeasureRepeat
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="measure-repeat" type="measure-repeat" />
"""
                                     ))


class XMLBeatRepeat(XMLElement):
    """
    The beat-repeat type is used to indicate that a single beat (but possibly many notes) is repeated. The slashes attribute specifies the number of slashes to use in the symbol. The use-dots attribute indicates whether or not to use dots as well (for instance, with mixed rhythm patterns). The value for slashes is 1 and the value for use-dots is no if not specified.
    
    The stop type indicates the first beat where the repeats are no longer displayed. Both the start and stop of the beat being repeated should be specified unless the repeats are displayed through the end of the part.
    
    The beat-repeat element specifies a notation style for repetitions. The actual music being repeated needs to be repeated within the MusicXML file. This element specifies the notation that indicates the repeat.\n
    XSD structure:\n
    Group\@name=slash\@minOccurs=0\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=slash-type\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=slash-dot\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=except-voice\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeBeatRepeat
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beat-repeat" type="beat-repeat" />
"""
                                     ))


class XMLSlash(XMLElement):
    """
    The slash type is used to indicate that slash notation is to be used. If the slash is on every beat, use-stems is no (the default). To indicate rhythms but not pitches, use-stems is set to yes. The type attribute indicates whether this is the start or stop of a slash notation style. The use-dots attribute works as for the beat-repeat element, and only has effect if use-stems is no.\n
    XSD structure:\n
    Group\@name=slash\@minOccurs=0\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=slash-type\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=slash-dot\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=except-voice\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeSlash
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="slash" type="slash" />
"""
                                     ))


class XMLStaffType(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeStaffType
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-type" type="staff-type" minOccurs="0" />
"""
                                     ))


class XMLStaffLines(XMLElement):
    """
    The staff-lines element specifies the number of lines and is usually used for a non 5-line staff. If the staff-lines element is present, the appearance of each line may be individually specified with a line-detail element.
    """
    
    TYPE = XSDSimpleTypeNonNegativeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-lines" type="xs:nonNegativeInteger">
    <xs:annotation>
        <xs:documentation>The staff-lines element specifies the number of lines and is usually used for a non 5-line staff. If the staff-lines element is present, the appearance of each line may be individually specified with a line-detail element. </xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLLineDetail(XMLElement):
    """
    If the staff-lines element is present, the appearance of each line may be individually specified with a line-detail type. Staff lines are numbered from bottom to top. The print-object attribute allows lines to be hidden within a staff. This is used in special situations such as a widely-spaced percussion staff where a note placed below the higher line is distinct from a note placed above the lower line. Hidden staff lines are included when specifying clef lines and determining display-step / display-octave values, but are not counted as lines for the purposes of the system-layout and staff-layout elements.
    """
    
    TYPE = XSDComplexTypeLineDetail
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="line-detail" type="line-detail" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLStaffTuning(XMLElement):
    """
    The staff-tuning type specifies the open, non-capo tuning of the lines on a tablature staff.\n
    XSD structure:\n
    Group\@name=tuning\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=tuning-step\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=tuning-alter\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=tuning-octave\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeStaffTuning
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-tuning" type="staff-tuning" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLCapo(XMLElement):
    """
    The capo element indicates at which fret a capo should be placed on a fretted instrument. This changes the open tuning of the strings specified by staff-tuning by the specified number of half-steps.
    """
    
    TYPE = XSDSimpleTypeNonNegativeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="capo" type="xs:nonNegativeInteger" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The capo element indicates at which fret a capo should be placed on a fretted instrument. This changes the open tuning of the strings specified by staff-tuning by the specified number of half-steps.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStaffSize(XMLElement):
    """
    The staff-size element indicates how large a staff space is on this staff, expressed as a percentage of the work's default scaling. Values less than 100 make the staff space smaller while values over 100 make the staff space larger. A staff-type of cue, ossia, or editorial implies a staff-size of less than 100, but the exact value is implementation-dependent unless specified here. Staff size affects staff height only, not the relationship of the staff to the left and right margins.
    
    In some cases, a staff-size different than 100 also scales the notation on the staff, such as with a cue staff. In other cases, such as percussion staves, the lines may be more widely spaced without scaling the notation on the staff. The scaling attribute allows these two cases to be distinguished. It specifies the percentage scaling that applies to the notation. Values less that 100 make the notation smaller while values over 100 make the notation larger. The staff-size content and scaling attribute are both non-negative decimal values.
    """
    
    TYPE = XSDComplexTypeStaffSize
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-size" type="staff-size" minOccurs="0" />
"""
                                     ))


class XMLInterchangeable(XMLElement):
    """
    The interchangeable type is used to represent the second in a pair of interchangeable dual time signatures, such as the 6/8 in 3/4 (6/8). A separate symbol attribute value is available compared to the time element's symbol attribute, which applies to the first of the dual time signatures.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=time-relation\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=time-signature\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=beats\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=beat-type\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeInterchangeable
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="interchangeable" type="interchangeable" minOccurs="0" />
"""
                                     ))


class XMLSenzaMisura(XMLElement):
    """
    A senza-misura element explicitly indicates that no time signature is present. The optional element content indicates the symbol to be used, if any, such as an X. The time element's symbol attribute is not used when a senza-misura element is present.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="senza-misura" type="xs:string">
    <xs:annotation>
        <xs:documentation>A senza-misura element explicitly indicates that no time signature is present. The optional element content indicates the symbol to be used, if any, such as an X. The time element's symbol attribute is not used when a senza-misura element is present.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBarStyle(XMLElement):
    """
    The bar-style-color type contains barline style and color information.
    """
    
    TYPE = XSDComplexTypeBarStyleColor
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bar-style" type="bar-style-color" minOccurs="0" />
"""
                                     ))


class XMLWavyLine(XMLElement):
    """
    Wavy lines are one way to indicate trills and vibrato. When used with a barline element, they should always have type="continue" set. The smufl attribute specifies a particular wavy line glyph from the SMuFL Multi-segment lines range.
    """
    
    TYPE = XSDComplexTypeWavyLine
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="wavy-line" type="wavy-line" minOccurs="0" />
"""
                                     ))


class XMLSegno(XMLElement):
    """
    The segno type is the visual indicator of a segno sign. The exact glyph can be specified with the smufl attribute. A sound element is also needed to guide playback applications reliably.
    """
    
    TYPE = XSDComplexTypeSegno
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="segno" type="segno" minOccurs="0" />
"""
                                     ))


class XMLCoda(XMLElement):
    """
    The coda type is the visual indicator of a coda sign. The exact glyph can be specified with the smufl attribute. A sound element is also needed to guide playback applications reliably.
    """
    
    TYPE = XSDComplexTypeCoda
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="coda" type="coda" minOccurs="0" />
"""
                                     ))


class XMLFermata(XMLElement):
    """
    The fermata text content represents the shape of the fermata sign. An empty fermata element represents a normal fermata. The fermata type is upright if not specified.
    """
    
    TYPE = XSDComplexTypeFermata
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fermata" type="fermata" minOccurs="0" maxOccurs="2" />
"""
                                     ))


class XMLEnding(XMLElement):
    """
    The ending type represents multiple (e.g. first and second) endings. Typically, the start type is associated with the left barline of the first measure in an ending. The stop and discontinue types are associated with the right barline of the last measure in an ending. Stop is used when the ending mark concludes with a downward jog, as is typical for first endings. Discontinue is used when there is no downward jog, as is typical for second endings that do not conclude a piece. The length of the jog can be specified using the end-length attribute. The text-x and text-y attributes are offsets that specify where the baseline of the start of the ending text appears, relative to the start of the ending line.
    
    The number attribute indicates which times the ending is played, similar to the time-only attribute used by other elements. While this often represents the numeric values for what is under the ending line, it can also indicate whether an ending is played during a larger dal segno or da capo repeat. Single endings such as "1" or comma-separated multiple endings such as "1,2" may be used. The ending element text is used when the text displayed in the ending is different than what appears in the number attribute. The print-object attribute is used to indicate when an ending is present but not printed, as is often the case for many parts in a full score.
    """
    
    TYPE = XSDComplexTypeEnding
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ending" type="ending" minOccurs="0" />
"""
                                     ))


class XMLRepeat(XMLElement):
    """
    The repeat type represents repeat marks. The start of the repeat has a forward direction while the end of the repeat has a backward direction. The times and after-jump attributes are only used with backward repeats that are not part of an ending. The times attribute indicates the number of times the repeated section is played. The after-jump attribute indicates if the repeats are played after a jump due to a da capo or dal segno.
    """
    
    TYPE = XSDComplexTypeRepeat
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="repeat" type="repeat" minOccurs="0" />
"""
                                     ))


class XMLAccordionHigh(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accordion-high" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The accordion-high element indicates the presence of a dot in the high (4') section of the registration symbol. This element is omitted if no dot is present.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLAccordionMiddle(XMLElement):
    """
    The accordion-middle element indicates the presence of 1 to 3 dots in the middle (8') section of the registration symbol. This element is omitted if no dots are present.
    """
    
    TYPE = XSDSimpleTypeAccordionMiddle
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accordion-middle" type="accordion-middle" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The accordion-middle element indicates the presence of 1 to 3 dots in the middle (8') section of the registration symbol. This element is omitted if no dots are present.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLAccordionLow(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accordion-low" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The accordion-low element indicates the presence of a dot in the low (16') section of the registration symbol. This element is omitted if no dot is present.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBassSeparator(XMLElement):
    """
    The style-text type represents a text element with a print-style attribute group.
    """
    
    TYPE = XSDComplexTypeStyleText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bass-separator" type="style-text" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The optional bass-separator element indicates that text, rather than a line or slash, separates the bass from what precedes it.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBassStep(XMLElement):
    """
    The bass-step type represents the pitch step of the bass of the current chord within the harmony element. The text attribute indicates how the bass should appear in a score if not using the element contents.
    """
    
    TYPE = XSDComplexTypeBassStep
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bass-step" type="bass-step" />
"""
                                     ))


class XMLBassAlter(XMLElement):
    """
    The harmony-alter type represents the chromatic alteration of the root, numeral, or bass of the current harmony-chord group within the harmony element. In some chord styles, the text of the preceding element may include alteration information. In that case, the print-object attribute of this type can be set to no. The location attribute indicates whether the alteration should appear to the left or the right of the preceding element. Its default value varies by element.
    """
    
    TYPE = XSDComplexTypeHarmonyAlter
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bass-alter" type="harmony-alter" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The bass-alter element represents the chromatic alteration of the bass of the current chord within the harmony element. In some chord styles, the text for the bass-step element may include bass-alter information. In that case, the print-object attribute of the bass-alter element can be set to no. The location attribute indicates whether the alteration should appear to the left or the right of the bass-step; it is right if not specified.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDegreeValue(XMLElement):
    """
    The content of the degree-value type is a number indicating the degree of the chord (1 for the root, 3 for third, etc). The text attribute specifies how the value of the degree should be displayed. The symbol attribute indicates that a symbol should be used in specifying the degree. If the symbol attribute is present, the value of the text attribute follows the symbol.
    """
    
    TYPE = XSDComplexTypeDegreeValue
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="degree-value" type="degree-value" />
"""
                                     ))


class XMLDegreeAlter(XMLElement):
    """
    The degree-alter type represents the chromatic alteration for the current degree. If the degree-type value is alter or subtract, the degree-alter value is relative to the degree already in the chord based on its kind element. If the degree-type value is add, the degree-alter is relative to a dominant chord (major and perfect intervals except for a minor seventh). The plus-minus attribute is used to indicate if plus and minus symbols should be used instead of sharp and flat symbols to display the degree alteration. It is no if not specified.
    """
    
    TYPE = XSDComplexTypeDegreeAlter
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="degree-alter" type="degree-alter" />
"""
                                     ))


class XMLDegreeType(XMLElement):
    """
    The degree-type type indicates if this degree is an addition, alteration, or subtraction relative to the kind of the current chord. The value of the degree-type element affects the interpretation of the value of the degree-alter element. The text attribute specifies how the type of the degree should be displayed.
    """
    
    TYPE = XSDComplexTypeDegreeType
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="degree-type" type="degree-type" />
"""
                                     ))


class XMLDirectionType(XMLElement):
    """
    Textual direction types may have more than 1 component due to multiple fonts. The dynamics element may also be used in the notations element. Attribute groups related to print suggestions apply to the individual direction-type, not to the overall direction.\n
    XSD structure:\n
    Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=rehearsal\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Element\@name=segno\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Element\@name=coda\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Choice\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=words\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=symbol\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=wedge\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=dynamics\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Element\@name=dashes\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=bracket\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pedal\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=metronome\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=octave-shift\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=harp-pedals\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=damp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=damp-all\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=eyeglasses\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=string-mute\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=scordatura\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=image\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=principal-voice\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=percussion\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Element\@name=accordion-registration\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=staff-divide\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=other-direction\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeDirectionType
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="direction-type" type="direction-type" maxOccurs="unbounded" />
"""
                                     ))


class XMLOffset(XMLElement):
    """
    An offset is represented in terms of divisions, and indicates where the direction will appear relative to the current musical location. The current musical location is always within the current measure, even at the end of a measure.
    
    The offset affects the visual appearance of the direction. If the sound attribute is "yes", then the offset affects playback and listening too. If the sound attribute is "no", then any sound or listening associated with the direction takes effect at the current location. The sound attribute is "no" by default for compatibility with earlier versions of the MusicXML format. If an element within a direction includes a default-x attribute, the offset value will be ignored when determining the appearance of that element.
    """
    
    TYPE = XSDComplexTypeOffset
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="offset" type="offset" minOccurs="0" />
"""
                                     ))


class XMLSound(XMLElement):
    """
    The sound element contains general playback parameters. They can stand alone within a part/measure, or be a component element within a direction.
    
    Tempo is expressed in quarter notes per minute. If 0, the sound-generating program should prompt the user at the time of compiling a sound (MIDI) file.
    
    Dynamics (or MIDI velocity) are expressed as a percentage of the default forte value (90 for MIDI 1.0).
    
    Dacapo indicates to go back to the beginning of the movement. When used it always has the value "yes".
    
    Segno and dalsegno are used for backwards jumps to a segno sign; coda and tocoda are used for forward jumps to a coda sign. If there are multiple jumps, the value of these parameters can be used to name and distinguish them. If segno or coda is used, the divisions attribute can also be used to indicate the number of divisions per quarter note. Otherwise sound and MIDI generating programs may have to recompute this.
    
    By default, a dalsegno or dacapo attribute indicates that the jump should occur the first time through, while a tocoda attribute indicates the jump should occur the second time through. The time that jumps occur can be changed by using the time-only attribute.
    
    The forward-repeat attribute indicates that a forward repeat sign is implied but not displayed. It is used for example in two-part forms with repeats, such as a minuet and trio where no repeat is displayed at the start of the trio. This usually occurs after a barline. When used it always has the value of "yes".
    
    The fine attribute follows the final note or rest in a movement with a da capo or dal segno direction. If numeric, the value represents the actual duration of the final note or rest, which can be ambiguous in written notation and different among parts and voices. The value may also be "yes" to indicate no change to the final duration.
    
    If the sound element applies only particular times through a repeat, the time-only attribute indicates which times to apply the sound element.
    
    Pizzicato in a sound element effects all following notes. Yes indicates pizzicato, no indicates arco.
    
    The pan and elevation attributes are deprecated in Version 2.0. The pan and elevation elements in the midi-instrument element should be used instead. The meaning of the pan and elevation attributes is the same as for the pan and elevation elements. If both are present, the mid-instrument elements take priority.
    
    The damper-pedal, soft-pedal, and sostenuto-pedal attributes effect playback of the three common piano pedals and their MIDI controller equivalents. The yes value indicates the pedal is depressed; no indicates the pedal is released. A numeric value from 0 to 100 may also be used for half pedaling. This value is the percentage that the pedal is depressed. A value of 0 is equivalent to no, and a value of 100 is equivalent to yes.
    
    Instrument changes, MIDI devices, MIDI instruments, and playback techniques are changed using the instrument-change, midi-device, midi-instrument, and play elements. When there are multiple instances of these elements, they should be grouped together by instrument using the id attribute values.
    
    The offset element is used to indicate that the sound takes place offset from the current score position. If the sound element is a child of a direction element, the sound offset element overrides the direction offset element if both elements are present. Note that the offset reflects the intended musical position for the change in sound. It should not be used to compensate for latency issues in particular hardware configurations.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=instrument-change\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=midi-device\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=midi-instrument\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=play\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=swing\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=offset\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeSound
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sound" type="sound" minOccurs="0" />
"""
                                     ))


class XMLListening(XMLElement):
    """
    The listen and listening types, new in Version 4.0, specify different ways that a score following or machine listening application can interact with a performer. The listening type handles interactions that change the state of the listening application from the specified point in the performance onward. If multiple child elements of the same type are present, they should have distinct player and/or time-only attributes.
    
    The offset element is used to indicate that the listening change takes place offset from the current score position. If the listening element is a child of a direction element, the listening offset element overrides the direction offset element if both elements are present. Note that the offset reflects the intended musical position for the change in state. It should not be used to compensate for latency issues in particular hardware configurations.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=sync\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=other-listening\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=offset\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeListening
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="listening" type="listening" minOccurs="0" />
"""
                                     ))


class XMLRehearsal(XMLElement):
    """
    The formatted-text-id type represents a text element with text-formatting and id attributes.
    """
    
    TYPE = XSDComplexTypeFormattedTextId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="rehearsal" type="formatted-text-id" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The rehearsal element specifies letters, numbers, and section names that are notated in the score for reference during rehearsal. The enclosure is square if not specified. The language is Italian ("it") if not specified. Left justification is used if not specified.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLWords(XMLElement):
    """
    The formatted-text-id type represents a text element with text-formatting and id attributes.
    """
    
    TYPE = XSDComplexTypeFormattedTextId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="words" type="formatted-text-id">
    <xs:annotation>
        <xs:documentation>The words element specifies a standard text direction. The enclosure is none if not specified. The language is Italian ("it") if not specified. Left justification is used if not specified.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSymbol(XMLElement):
    """
    The formatted-symbol-id type represents a SMuFL musical symbol element with formatting and id attributes.
    """
    
    TYPE = XSDComplexTypeFormattedSymbolId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="symbol" type="formatted-symbol-id">
    <xs:annotation>
        <xs:documentation>The symbol element specifies a musical symbol using a canonical SMuFL glyph name. It is used when an occasional musical symbol is interspersed into text. It should not be used in place of semantic markup, such as metronome marks that mix text and symbols. Left justification is used if not specified. Enclosure is none if not specified.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLWedge(XMLElement):
    """
    The wedge type represents crescendo and diminuendo wedge symbols. The type attribute is crescendo for the start of a wedge that is closed at the left side, and diminuendo for the start of a wedge that is closed on the right side. Spread values are measured in tenths; those at the start of a crescendo wedge or end of a diminuendo wedge are ignored. The niente attribute is yes if a circle appears at the point of the wedge, indicating a crescendo from nothing or diminuendo to nothing. It is no by default, and used only when the type is crescendo, or the type is stop for a wedge that began with a diminuendo type. The line-type is solid if not specified.
    """
    
    TYPE = XSDComplexTypeWedge
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="wedge" type="wedge" />
"""
                                     ))


class XMLDynamics(XMLElement):
    """
    Dynamics can be associated either with a note or a general musical direction. To avoid inconsistencies between and amongst the letter abbreviations for dynamics (what is sf vs. sfz, standing alone or with a trailing dynamic that is not always piano), we use the actual letters as the names of these dynamic elements. The other-dynamics element allows other dynamic marks that are not covered here. Dynamics elements may also be combined to create marks not covered by a single element, such as sfmp.
    
    These letter dynamic symbols are separated from crescendo, decrescendo, and wedge indications. Dynamic representation is inconsistent in scores. Many things are assumed by the composer and left out, such as returns to original dynamics. The MusicXML format captures what is in the score, but does not try to be optimal for analysis or synthesis of dynamics.
    
    The placement attribute is used when the dynamics are associated with a note. It is ignored when the dynamics are associated with a direction. In that case the direction element's placement attribute is used instead.\n
    XSD structure:\n
    Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=p\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=ppp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pppp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=ppppp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pppppp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=f\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=ff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=ffff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fffff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=ffffff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=mp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=mf\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=sf\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=sfp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=sfpp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=rf\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=rfz\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=sfz\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=sffz\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fz\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=n\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pf\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=sfzp\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=other-dynamics\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeDynamics
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="dynamics" type="dynamics" maxOccurs="unbounded" />
"""
                                     ))


class XMLDashes(XMLElement):
    """
    The dashes type represents dashes, used for instance with cresc. and dim. marks.
    """
    
    TYPE = XSDComplexTypeDashes
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="dashes" type="dashes" />
"""
                                     ))


class XMLBracket(XMLElement):
    """
    Brackets are combined with words in a variety of modern directions. The line-end attribute specifies if there is a jog up or down (or both), an arrow, or nothing at the start or end of the bracket. If the line-end is up or down, the length of the jog can be specified using the end-length attribute. The line-type is solid if not specified.
    """
    
    TYPE = XSDComplexTypeBracket
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bracket" type="bracket" />
"""
                                     ))


class XMLPedal(XMLElement):
    """
    The pedal type represents piano pedal marks, including damper and sostenuto pedal marks. The line attribute is yes if pedal lines are used. The sign attribute is yes if Ped, Sost, and * signs are used. For compatibility with older versions, the sign attribute is yes by default if the line attribute is no, and is no by default if the line attribute is yes. If the sign attribute is set to yes and the type is start or sostenuto, the abbreviated attribute is yes if the short P and S signs are used, and no if the full Ped and Sost signs are used. It is no by default. Otherwise the abbreviated attribute is ignored. The alignment attributes are ignored if the sign attribute is no.
    """
    
    TYPE = XSDComplexTypePedal
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pedal" type="pedal" />
"""
                                     ))


class XMLMetronome(XMLElement):
    """
    The metronome type represents metronome marks and other metric relationships. The beat-unit group and per-minute element specify regular metronome marks. The metronome-note and metronome-relation elements allow for the specification of metric modulations and other metric relationships, such as swing tempo marks where two eighths are equated to a quarter note / eighth note triplet. Tied notes can be represented in both types of metronome marks by using the beat-unit-tied and metronome-tied elements. The parentheses attribute indicates whether or not to put the metronome mark in parentheses; its value is no if not specified. The print-object attribute is set to no in cases where the metronome element represents a relationship or range that is not displayed in the music notation.\n
    XSD structure:\n
    Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Group\@name=beat-unit\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=beat-unit\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=beat-unit-dot\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=beat-unit-tied\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=per-minute\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Group\@name=beat-unit\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=beat-unit\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=beat-unit-dot\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- \- \- \- \- Element\@name=beat-unit-tied\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=metronome-arrows\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=metronome-note\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=metronome-relation\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=metronome-note\@minOccurs=1\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeMetronome
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome" type="metronome" />
"""
                                     ))


class XMLOctaveShift(XMLElement):
    """
    The octave shift type indicates where notes are shifted up or down from their true pitched values because of printing difficulty. Thus a treble clef line noted with 8va will be indicated with an octave-shift down from the pitch data indicated in the notes. A size of 8 indicates one octave; a size of 15 indicates two octaves.
    """
    
    TYPE = XSDComplexTypeOctaveShift
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="octave-shift" type="octave-shift" />
"""
                                     ))


class XMLHarpPedals(XMLElement):
    """
    The harp-pedals type is used to create harp pedal diagrams. The pedal-step and pedal-alter elements use the same values as the step and alter elements. For easiest reading, the pedal-tuning elements should follow standard harp pedal order, with pedal-step values of D, C, B, E, F, G, and A.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pedal-tuning\@minOccurs=1\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeHarpPedals
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="harp-pedals" type="harp-pedals" />
"""
                                     ))


class XMLDamp(XMLElement):
    """
    The empty-print-style-align-id type represents an empty element with print-style-align and optional-unique-id attribute groups.
    """
    
    TYPE = XSDComplexTypeEmptyPrintStyleAlignId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="damp" type="empty-print-style-align-id">
    <xs:annotation>
        <xs:documentation>The damp element specifies a harp damping mark.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDampAll(XMLElement):
    """
    The empty-print-style-align-id type represents an empty element with print-style-align and optional-unique-id attribute groups.
    """
    
    TYPE = XSDComplexTypeEmptyPrintStyleAlignId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="damp-all" type="empty-print-style-align-id">
    <xs:annotation>
        <xs:documentation>The damp-all element specifies a harp damping mark for all strings.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLEyeglasses(XMLElement):
    """
    The empty-print-style-align-id type represents an empty element with print-style-align and optional-unique-id attribute groups.
    """
    
    TYPE = XSDComplexTypeEmptyPrintStyleAlignId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="eyeglasses" type="empty-print-style-align-id">
    <xs:annotation>
        <xs:documentation>The eyeglasses element represents the eyeglasses symbol, common in commercial music.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStringMute(XMLElement):
    """
    The string-mute type represents string mute on and mute off symbols.
    """
    
    TYPE = XSDComplexTypeStringMute
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="string-mute" type="string-mute" />
"""
                                     ))


class XMLScordatura(XMLElement):
    """
    Scordatura string tunings are represented by a series of accord elements, similar to the staff-tuning elements. Strings are numbered from high to low.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=accord\@minOccurs=1\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeScordatura
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="scordatura" type="scordatura" />
"""
                                     ))


class XMLImage(XMLElement):
    """
    The image type is used to include graphical images in a score.
    """
    
    TYPE = XSDComplexTypeImage
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="image" type="image" />
"""
                                     ))


class XMLPrincipalVoice(XMLElement):
    """
    The principal-voice type represents principal and secondary voices in a score, either for analysis or for square bracket symbols that appear in a score. The element content is used for analysis and may be any text value. The symbol attribute indicates the type of symbol used. When used for analysis separate from any printed score markings, it should be set to none. Otherwise if the type is stop it should be set to plain.
    """
    
    TYPE = XSDComplexTypePrincipalVoice
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="principal-voice" type="principal-voice" />
"""
                                     ))


class XMLPercussion(XMLElement):
    """
    The percussion element is used to define percussion pictogram symbols. Definitions for these symbols can be found in Kurt Stone's "Music Notation in the Twentieth Century" on pages 206-212 and 223. Some values are added to these based on how usage has evolved in the 30 years since Stone's book was published.\n
    XSD structure:\n
    Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=glass\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=metal\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=wood\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pitched\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=membrane\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=effect\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=timpani\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=beater\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=stick\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=stick-location\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=other-percussion\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePercussion
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="percussion" type="percussion" maxOccurs="unbounded" />
"""
                                     ))


class XMLAccordionRegistration(XMLElement):
    """
    The accordion-registration type is used for accordion registration symbols. These are circular symbols divided horizontally into high, middle, and low sections that correspond to 4', 8', and 16' pipes. Each accordion-high, accordion-middle, and accordion-low element represents the presence of one or more dots in the registration diagram. An accordion-registration element needs to have at least one of the child elements present.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=accordion-high\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=accordion-middle\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=accordion-low\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeAccordionRegistration
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accordion-registration" type="accordion-registration" />
"""
                                     ))


class XMLStaffDivide(XMLElement):
    """
    The staff-divide element represents the staff division arrow symbols found at SMuFL code points U+E00B, U+E00C, and U+E00D.
    """
    
    TYPE = XSDComplexTypeStaffDivide
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-divide" type="staff-divide" />
"""
                                     ))


class XMLOtherDirection(XMLElement):
    """
    The other-direction type is used to define any direction symbols not yet in the MusicXML format. The smufl attribute can be used to specify a particular direction symbol, allowing application interoperability without requiring every SMuFL glyph to have a MusicXML element equivalent. Using the other-direction type without the smufl attribute allows for extended representation, though without application interoperability.
    """
    
    TYPE = XSDComplexTypeOtherDirection
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-direction" type="other-direction" />
"""
                                     ))


class XMLFrameStrings(XMLElement):
    """
    The frame-strings element gives the overall size of the frame in vertical lines (strings).
    """
    
    TYPE = XSDSimpleTypePositiveInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="frame-strings" type="xs:positiveInteger">
    <xs:annotation>
        <xs:documentation>The frame-strings element gives the overall size of the frame in vertical lines (strings).</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLFrameFrets(XMLElement):
    """
    The frame-frets element gives the overall size of the frame in horizontal spaces (frets).
    """
    
    TYPE = XSDSimpleTypePositiveInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="frame-frets" type="xs:positiveInteger">
    <xs:annotation>
        <xs:documentation>The frame-frets element gives the overall size of the frame in horizontal spaces (frets).</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLFirstFret(XMLElement):
    """
    The first-fret type indicates which fret is shown in the top space of the frame; it is fret 1 if the element is not present. The optional text attribute indicates how this is represented in the fret diagram, while the location attribute indicates whether the text appears to the left or right of the frame.
    """
    
    TYPE = XSDComplexTypeFirstFret
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="first-fret" type="first-fret" minOccurs="0" />
"""
                                     ))


class XMLFrameNote(XMLElement):
    """
    The frame-note type represents each note included in the frame. An open string will have a fret value of 0, while a muted string will not be associated with a frame-note element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=string\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fret\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fingering\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=barre\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeFrameNote
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="frame-note" type="frame-note" maxOccurs="unbounded" />
"""
                                     ))


class XMLString(XMLElement):
    """
    The string type is used with tablature notation, regular notation (where it is often circled), and chord diagrams. String numbers start with 1 for the highest pitched full-length string.
    """
    
    TYPE = XSDComplexTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="string" type="string" />
"""
                                     ))


class XMLFret(XMLElement):
    """
    The fret element is used with tablature notation and chord diagrams. Fret numbers start with 0 for an open string and 1 for the first fret.
    """
    
    TYPE = XSDComplexTypeFret
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fret" type="fret" />
"""
                                     ))


class XMLFingering(XMLElement):
    """
    Fingering is typically indicated 1,2,3,4,5. Multiple fingerings may be given, typically to substitute fingerings in the middle of a note. The substitution and alternate values are "no" if the attribute is not present. For guitar and other fretted instruments, the fingering element represents the fretting finger; the pluck element represents the plucking finger.
    """
    
    TYPE = XSDComplexTypeFingering
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fingering" type="fingering" minOccurs="0" />
"""
                                     ))


class XMLBarre(XMLElement):
    """
    The barre element indicates placing a finger over multiple strings on a single fret. The type is "start" for the lowest pitched string (e.g., the string with the highest MusicXML number) and is "stop" for the highest pitched string.
    """
    
    TYPE = XSDComplexTypeBarre
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="barre" type="barre" minOccurs="0" />
"""
                                     ))


class XMLFeature(XMLElement):
    """
    The feature type is a part of the grouping element used for musical analysis. The type attribute represents the type of the feature and the element content represents its value. This type is flexible to allow for different analyses.
    """
    
    TYPE = XSDComplexTypeFeature
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="feature" type="feature" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLFrame(XMLElement):
    """
    The frame type represents a frame or fretboard diagram used together with a chord symbol. The representation is based on the NIFF guitar grid with additional information. The frame type's unplayed attribute indicates what to display above a string that has no associated frame-note element. Typical values are x and the empty string. If the attribute is not present, the display of the unplayed string is application-defined.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=frame-strings\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=frame-frets\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=first-fret\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=frame-note\@minOccurs=1\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeFrame
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="frame" type="frame" minOccurs="0" />
"""
                                     ))


class XMLPedalTuning(XMLElement):
    """
    The pedal-tuning type specifies the tuning of a single harp pedal.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pedal-step\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pedal-alter\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePedalTuning
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pedal-tuning" type="pedal-tuning" maxOccurs="unbounded" />
"""
                                     ))


class XMLSync(XMLElement):
    """
    The sync type specifies the style that a score following application should use the synchronize an accompaniment with a performer. If this type is not included in a score, default synchronization depends on the application.
    
    The optional latency attribute specifies a time in milliseconds that the listening application should expect from the performer. The optional player and time-only attributes restrict the element to apply to a single player or set of times through a repeated section, respectively.
    """
    
    TYPE = XSDComplexTypeSync
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sync" type="sync" />
"""
                                     ))


class XMLOtherListening(XMLElement):
    """
    The other-listening type represents other types of listening control and interaction. The required type attribute indicates the type of listening to which the element content applies. The optional player and time-only attributes restrict the element to apply to a single player or set of times through a repeated section, respectively.
    """
    
    TYPE = XSDComplexTypeOtherListening
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-listening" type="other-listening" />
"""
                                     ))


class XMLBeatUnitTied(XMLElement):
    """
    The beat-unit-tied type indicates a beat-unit within a metronome mark that is tied to the preceding beat-unit. This allows two or more tied notes to be associated with a per-minute value in a metronome mark, whereas the metronome-tied element is restricted to metric relationship marks.\n
    XSD structure:\n
    Group\@name=beat-unit\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=beat-unit\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=beat-unit-dot\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeBeatUnitTied
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beat-unit-tied" type="beat-unit-tied" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLPerMinute(XMLElement):
    """
    The per-minute type can be a number, or a text description including numbers. If a font is specified, it overrides the font specified for the overall metronome element. This allows separate specification of a music font for the beat-unit and a text font for the numeric value, in cases where a single metronome font is not used.
    """
    
    TYPE = XSDComplexTypePerMinute
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="per-minute" type="per-minute" />
"""
                                     ))


class XMLMetronomeArrows(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-arrows" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>If the metronome-arrows element is present, it indicates that metric modulation arrows are displayed on both sides of the metronome mark.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMetronomeNote(XMLElement):
    """
    The metronome-note type defines the appearance of a note within a metric relationship mark.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=metronome-type\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=metronome-dot\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=metronome-beam\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=metronome-tied\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=metronome-tuplet\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeMetronomeNote
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-note" type="metronome-note" maxOccurs="unbounded" />
"""
                                     ))


class XMLMetronomeRelation(XMLElement):
    """
    The metronome-relation element describes the relationship symbol that goes between the two sets of metronome-note elements. The currently allowed value is equals, but this may expand in future versions. If the element is empty, the equals value is used.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-relation" type="xs:string">
    <xs:annotation>
        <xs:documentation>The metronome-relation element describes the relationship symbol that goes between the two sets of metronome-note elements. The currently allowed value is equals, but this may expand in future versions. If the element is empty, the equals value is used.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMetronomeType(XMLElement):
    """
    The metronome-type element works like the type element in defining metric relationships.
    """
    
    TYPE = XSDSimpleTypeNoteTypeValue
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-type" type="note-type-value">
    <xs:annotation>
        <xs:documentation>The metronome-type element works like the type element in defining metric relationships.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMetronomeDot(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-dot" type="empty" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The metronome-dot element works like the dot element in defining metric relationships.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMetronomeBeam(XMLElement):
    """
    The metronome-beam type works like the beam type in defining metric relationships, but does not include all the attributes available in the beam type.
    """
    
    TYPE = XSDComplexTypeMetronomeBeam
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-beam" type="metronome-beam" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLMetronomeTied(XMLElement):
    """
    The metronome-tied indicates the presence of a tie within a metric relationship mark. As with the tied element, both the start and stop of the tie should be specified, in this case within separate metronome-note elements.
    """
    
    TYPE = XSDComplexTypeMetronomeTied
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-tied" type="metronome-tied" minOccurs="0" />
"""
                                     ))


class XMLMetronomeTuplet(XMLElement):
    """
    The metronome-tuplet type uses the same element structure as the time-modification element along with some attributes from the tuplet element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=actual-notes\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=normal-notes\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=normal-type\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=normal-dot\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeMetronomeTuplet
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metronome-tuplet" type="metronome-tuplet" minOccurs="0" />
"""
                                     ))


class XMLNumeralRoot(XMLElement):
    """
    The numeral-root type represents the Roman numeral or Nashville number as a positive integer from 1 to 7. The text attribute indicates how the numeral should appear in the score. A numeral-root value of 5 with a kind of major would have a text attribute of "V" if displayed as a Roman numeral, and "5" if displayed as a Nashville number. If the text attribute is not specified, the display is application-dependent.
    """
    
    TYPE = XSDComplexTypeNumeralRoot
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="numeral-root" type="numeral-root" />
"""
                                     ))


class XMLNumeralAlter(XMLElement):
    """
    The harmony-alter type represents the chromatic alteration of the root, numeral, or bass of the current harmony-chord group within the harmony element. In some chord styles, the text of the preceding element may include alteration information. In that case, the print-object attribute of this type can be set to no. The location attribute indicates whether the alteration should appear to the left or the right of the preceding element. Its default value varies by element.
    """
    
    TYPE = XSDComplexTypeHarmonyAlter
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="numeral-alter" type="harmony-alter" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The numeral-alter element represents an alteration to the numeral-root, similar to the alter element for a pitch. The print-object attribute can be used to hide an alteration in cases such as when the MusicXML encoding of a 6 or 7 numeral-root in a minor key requires an alteration that is not displayed. The location attribute indicates whether the alteration should appear to the left or the right of the numeral-root. It is left by default.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLNumeralKey(XMLElement):
    """
    The numeral-key type is used when the key for the numeral is different than the key specified by the key signature. The numeral-fifths element specifies the key in the same way as the fifths element. The numeral-mode element specifies the mode similar to the mode element, but with a restricted set of values\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=numeral-fifths\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=numeral-mode\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNumeralKey
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="numeral-key" type="numeral-key" minOccurs="0" />
"""
                                     ))


class XMLNumeralFifths(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeFifths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="numeral-fifths" type="fifths" />
"""
                                     ))


class XMLNumeralMode(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeNumeralMode
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="numeral-mode" type="numeral-mode" />
"""
                                     ))


class XMLPedalStep(XMLElement):
    """
    The pedal-step element defines the pitch step for a single harp pedal.
    """
    
    TYPE = XSDSimpleTypeStep
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pedal-step" type="step">
    <xs:annotation>
        <xs:documentation>The pedal-step element defines the pitch step for a single harp pedal.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPedalAlter(XMLElement):
    """
    The pedal-alter element defines the chromatic alteration for a single harp pedal.
    """
    
    TYPE = XSDSimpleTypeSemitones
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pedal-alter" type="semitones">
    <xs:annotation>
        <xs:documentation>The pedal-alter element defines the chromatic alteration for a single harp pedal.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLGlass(XMLElement):
    """
    The glass type represents pictograms for glass percussion instruments. The smufl attribute is used to distinguish different SMuFL glyphs for wind chimes in the Chimes pictograms range, including those made of materials other than glass.
    """
    
    TYPE = XSDComplexTypeGlass
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="glass" type="glass" />
"""
                                     ))


class XMLMetal(XMLElement):
    """
    The metal type represents pictograms for metal percussion instruments. The smufl attribute is used to distinguish different SMuFL stylistic alternates.
    """
    
    TYPE = XSDComplexTypeMetal
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="metal" type="metal" />
"""
                                     ))


class XMLWood(XMLElement):
    """
    The wood type represents pictograms for wood percussion instruments. The smufl attribute is used to distinguish different SMuFL stylistic alternates.
    """
    
    TYPE = XSDComplexTypeWood
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="wood" type="wood" />
"""
                                     ))


class XMLPitched(XMLElement):
    """
    The pitched-value type represents pictograms for pitched percussion instruments. The smufl attribute is used to distinguish different SMuFL glyphs for a particular pictogram within the Tuned mallet percussion pictograms range.
    """
    
    TYPE = XSDComplexTypePitched
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pitched" type="pitched" />
"""
                                     ))


class XMLMembrane(XMLElement):
    """
    The membrane type represents pictograms for membrane percussion instruments. The smufl attribute is used to distinguish different SMuFL stylistic alternates.
    """
    
    TYPE = XSDComplexTypeMembrane
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="membrane" type="membrane" />
"""
                                     ))


class XMLEffect(XMLElement):
    """
    The effect type represents pictograms for sound effect percussion instruments. The smufl attribute is used to distinguish different SMuFL stylistic alternates.
    """
    
    TYPE = XSDComplexTypeEffect
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="effect" type="effect" />
"""
                                     ))


class XMLTimpani(XMLElement):
    """
    The timpani type represents the timpani pictogram. The smufl attribute is used to distinguish different SMuFL stylistic alternates.
    """
    
    TYPE = XSDComplexTypeTimpani
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="timpani" type="timpani" />
"""
                                     ))


class XMLBeater(XMLElement):
    """
    The beater type represents pictograms for beaters, mallets, and sticks that do not have different materials represented in the pictogram.
    """
    
    TYPE = XSDComplexTypeBeater
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beater" type="beater" />
"""
                                     ))


class XMLStick(XMLElement):
    """
    The stick type represents pictograms where the material of the stick, mallet, or beater is included.The parentheses and dashed-circle attributes indicate the presence of these marks around the round beater part of a pictogram. Values for these attributes are "no" if not present.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=stick-type\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=stick-material\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeStick
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="stick" type="stick" />
"""
                                     ))


class XMLStickLocation(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeStickLocation
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="stick-location" type="stick-location" />
"""
                                     ))


class XMLOtherPercussion(XMLElement):
    """
    The other-text type represents a text element with a smufl attribute group. This type is used by MusicXML direction extension elements to allow specification of specific SMuFL glyphs without needed to add every glyph as a MusicXML element.
    """
    
    TYPE = XSDComplexTypeOtherText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-percussion" type="other-text">
    <xs:annotation>
        <xs:documentation>The other-percussion element represents percussion pictograms not defined elsewhere.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMeasureLayout(XMLElement):
    """
    The measure-layout type includes the horizontal distance from the previous measure. It applies to the current measure only.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=measure-distance\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeMeasureLayout
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="measure-layout" type="measure-layout" minOccurs="0" />
"""
                                     ))


class XMLMeasureNumbering(XMLElement):
    """
    The measure-numbering type describes how frequently measure numbers are displayed on this part. The text attribute from the measure element is used for display, or the number attribute if the text attribute is not present. Measures with an implicit attribute set to "yes" never display a measure number, regardless of the measure-numbering setting.
    
    The optional staff attribute refers to staff numbers within the part, from top to bottom on the system. It indicates which staff is used as the reference point for vertical positioning. A value of 1 is assumed if not present.
    
    The optional multiple-rest-always and multiple-rest-range attributes describe how measure numbers are shown on multiple rests when the measure-numbering value is not set to none. The multiple-rest-always attribute is set to yes when the measure number should always be shown, even if the multiple rest starts midway through a system when measure numbering is set to system level. The multiple-rest-range attribute is set to yes when measure numbers on multiple rests display the range of numbers for the first and last measure, rather than just the number of the first measure.
    """
    
    TYPE = XSDComplexTypeMeasureNumbering
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="measure-numbering" type="measure-numbering" minOccurs="0" />
"""
                                     ))


class XMLPartNameDisplay(XMLElement):
    """
    The name-display type is used for exact formatting of multi-font text in part and group names to the left of the system. The print-object attribute can be used to determine what, if anything, is printed at the start of each system. Enclosure for the display-text element is none by default. Language for the display-text element is Italian ("it") by default.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=display-text\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=accidental-text\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNameDisplay
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-name-display" type="name-display" minOccurs="0" />
"""
                                     ))


class XMLPartAbbreviationDisplay(XMLElement):
    """
    The name-display type is used for exact formatting of multi-font text in part and group names to the left of the system. The print-object attribute can be used to determine what, if anything, is printed at the start of each system. Enclosure for the display-text element is none by default. Language for the display-text element is Italian ("it") by default.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=display-text\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=accidental-text\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNameDisplay
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-abbreviation-display" type="name-display" minOccurs="0" />
"""
                                     ))


class XMLRootStep(XMLElement):
    """
    The root-step type represents the pitch step of the root of the current chord within the harmony element. The text attribute indicates how the root should appear in a score if not using the element contents.
    """
    
    TYPE = XSDComplexTypeRootStep
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="root-step" type="root-step" />
"""
                                     ))


class XMLRootAlter(XMLElement):
    """
    The harmony-alter type represents the chromatic alteration of the root, numeral, or bass of the current harmony-chord group within the harmony element. In some chord styles, the text of the preceding element may include alteration information. In that case, the print-object attribute of this type can be set to no. The location attribute indicates whether the alteration should appear to the left or the right of the preceding element. Its default value varies by element.
    """
    
    TYPE = XSDComplexTypeHarmonyAlter
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="root-alter" type="harmony-alter" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The root-alter element represents the chromatic alteration of the root of the current chord within the harmony element. In some chord styles, the text for the root-step element may include root-alter information. In that case, the print-object attribute of the root-alter element can be set to no. The location attribute indicates whether the alteration should appear to the left or the right of the root-step; it is right by default.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLAccord(XMLElement):
    """
    The accord type represents the tuning of a single string in the scordatura element. It uses the same group of elements as the staff-tuning element. Strings are numbered from high to low.\n
    XSD structure:\n
    Group\@name=tuning\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=tuning-step\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=tuning-alter\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=tuning-octave\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeAccord
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accord" type="accord" maxOccurs="unbounded" />
"""
                                     ))


class XMLInstrumentChange(XMLElement):
    """
    The instrument-change element type represents a change to the virtual instrument sound for a given score-instrument. The id attribute refers to the score-instrument affected by the change. All instrument-change child elements can also be initially specified within the score-instrument element.\n
    XSD structure:\n
    Group\@name=virtual-instrument-data\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=instrument-sound\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Choice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=solo\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=ensemble\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=virtual-instrument\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeInstrumentChange
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="instrument-change" type="instrument-change" minOccurs="0" />
"""
                                     ))


class XMLMidiDevice(XMLElement):
    """
    The midi-device type corresponds to the DeviceName meta event in Standard MIDI Files. The optional port attribute is a number from 1 to 16 that can be used with the unofficial MIDI 1.0 port (or cable) meta event. Unlike the DeviceName meta event, there can be multiple midi-device elements per MusicXML part. The optional id attribute refers to the score-instrument assigned to this device. If missing, the device assignment affects all score-instrument elements in the score-part.
    """
    
    TYPE = XSDComplexTypeMidiDevice
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="midi-device" type="midi-device" minOccurs="0" />
"""
                                     ))


class XMLMidiInstrument(XMLElement):
    """
    The midi-instrument type defines MIDI 1.0 instrument playback. The midi-instrument element can be a part of either the score-instrument element at the start of a part, or the sound element within a part. The id attribute refers to the score-instrument affected by the change.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=midi-channel\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=midi-name\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=midi-bank\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=midi-program\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=midi-unpitched\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=volume\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=pan\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=elevation\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeMidiInstrument
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="midi-instrument" type="midi-instrument" minOccurs="0" />
"""
                                     ))


class XMLPlay(XMLElement):
    """
    The play type specifies playback techniques to be used in conjunction with the instrument-sound element. When used as part of a sound element, it applies to all notes going forward in score order. In multi-instrument parts, the affected instrument should be specified using the id attribute. When used as part of a note element, it applies to the current note only.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=ipa\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=mute\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=semi-pitched\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=other-play\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePlay
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="play" type="play" minOccurs="0" />
"""
                                     ))


class XMLSwing(XMLElement):
    """
    The swing element specifies whether or not to use swing playback, where consecutive on-beat / off-beat eighth or 16th notes are played with unequal nominal durations. 
    
    The straight element specifies that no swing is present, so consecutive notes have equal durations.
    
    The first and second elements are positive integers that specify the ratio between durations of consecutive notes. For example, a first element with a value of 2 and a second element with a value of 1 applied to eighth notes specifies a quarter note / eighth note tuplet playback, where the first note is twice as long as the second note. Ratios should be specified with the smallest integers possible. For example, a ratio of 6 to 4 should be specified as 3 to 2 instead.
    
    The optional swing-type element specifies the note type, either eighth or 16th, to which the ratio is applied. The value is eighth if this element is not present.
    
    The optional swing-style element is a string describing the style of swing used.
    
    The swing element has no effect for playback of grace notes, notes where a type element is not present, and notes where the specified duration is different than the nominal value associated with the specified type. If a swung note has attack and release attributes, those values modify the swung playback.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=straight\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=first\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=second\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=swing-type\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=swing-style\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeSwing
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="swing" type="swing" minOccurs="0" />
"""
                                     ))


class XMLStickType(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeStickType
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="stick-type" type="stick-type" />
"""
                                     ))


class XMLStickMaterial(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeStickMaterial
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="stick-material" type="stick-material" />
"""
                                     ))


class XMLStraight(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="straight" type="empty" />
"""
                                     ))


class XMLFirst(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypePositiveInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="first" type="xs:positiveInteger" />
"""
                                     ))


class XMLSecond(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypePositiveInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="second" type="xs:positiveInteger" />
"""
                                     ))


class XMLSwingType(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeSwingTypeValue
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="swing-type" type="swing-type-value" minOccurs="0" />
"""
                                     ))


class XMLSwingStyle(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="swing-style" type="xs:string" minOccurs="0" />
"""
                                     ))


class XMLEncodingDate(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeYyyyMmDd
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="encoding-date" type="yyyy-mm-dd" />
"""
                                     ))


class XMLEncoder(XMLElement):
    """
    The typed-text type represents a text element with a type attribute.
    """
    
    TYPE = XSDComplexTypeTypedText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="encoder" type="typed-text" />
"""
                                     ))


class XMLSoftware(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="software" type="xs:string" />
"""
                                     ))


class XMLEncodingDescription(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="encoding-description" type="xs:string" />
"""
                                     ))


class XMLSupports(XMLElement):
    """
    The supports type indicates if a MusicXML encoding supports a particular MusicXML element. This is recommended for elements like beam, stem, and accidental, where the absence of an element is ambiguous if you do not know if the encoding supports that element. For Version 2.0, the supports element is expanded to allow programs to indicate support for particular attributes or particular values. This lets applications communicate, for example, that all system and/or page breaks are contained in the MusicXML file.
    """
    
    TYPE = XSDComplexTypeSupports
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="supports" type="supports" />
"""
                                     ))


class XMLCreator(XMLElement):
    """
    The typed-text type represents a text element with a type attribute.
    """
    
    TYPE = XSDComplexTypeTypedText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="creator" type="typed-text" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The creator element is borrowed from Dublin Core. It is used for the creators of the score. The type attribute is used to distinguish different creative contributions. Thus, there can be multiple creators within an identification. Standard type values are composer, lyricist, and arranger. Other type values may be used for different types of creative roles. The type attribute should usually be used even if there is just a single creator element. The MusicXML format does not use the creator / contributor distinction from Dublin Core.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLRights(XMLElement):
    """
    The typed-text type represents a text element with a type attribute.
    """
    
    TYPE = XSDComplexTypeTypedText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="rights" type="typed-text" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The rights element is borrowed from Dublin Core. It contains copyright and other intellectual property notices. Words, music, and derivatives can have different types, so multiple rights elements with different type attributes are supported. Standard type values are music, words, and arrangement, but other types may be used. The type attribute is only needed when there are multiple rights elements.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLEncoding(XMLElement):
    """
    The encoding element contains information about who did the digital encoding, when, with what software, and in what aspects. Standard type values for the encoder element are music, words, and arrangement, but other types may be used. The type attribute is only needed when there are multiple encoder elements.\n
    XSD structure:\n
    Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=encoding-date\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=encoder\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=software\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=encoding-description\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=supports\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeEncoding
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="encoding" type="encoding" minOccurs="0" />
"""
                                     ))


class XMLSource(XMLElement):
    """
    The source for the music that is encoded. This is similar to the Dublin Core source element.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="source" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The source for the music that is encoded. This is similar to the Dublin Core source element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLRelation(XMLElement):
    """
    The typed-text type represents a text element with a type attribute.
    """
    
    TYPE = XSDComplexTypeTypedText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="relation" type="typed-text" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>A related resource for the music that is encoded. This is similar to the Dublin Core relation element. Standard type values are music, words, and arrangement, but other types may be used.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMiscellaneous(XMLElement):
    """
    If a program has other metadata not yet supported in the MusicXML format, it can go in the miscellaneous element. The miscellaneous type puts each separate part of metadata into its own miscellaneous-field type.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=miscellaneous-field\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeMiscellaneous
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="miscellaneous" type="miscellaneous" minOccurs="0" />
"""
                                     ))


class XMLMiscellaneousField(XMLElement):
    """
    If a program has other metadata not yet supported in the MusicXML format, each type of metadata can go in a miscellaneous-field element. The required name attribute indicates the type of metadata the element content represents.
    """
    
    TYPE = XSDComplexTypeMiscellaneousField
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="miscellaneous-field" type="miscellaneous-field" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLLineWidth(XMLElement):
    """
    The line-width type indicates the width of a line type in tenths. The type attribute defines what type of line is being defined. Values include beam, bracket, dashes, enclosure, ending, extend, heavy barline, leger, light barline, octave shift, pedal, slur middle, slur tip, staff, stem, tie middle, tie tip, tuplet bracket, and wedge. The text content is expressed in tenths.
    """
    
    TYPE = XSDComplexTypeLineWidth
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="line-width" type="line-width" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLNoteSize(XMLElement):
    """
    The note-size type indicates the percentage of the regular note size to use for notes with a cue and large size as defined in the type element. The grace type is used for notes of cue size that that include a grace element. The cue type is used for all other notes with cue size, whether defined explicitly or implicitly via a cue element. The large type is used for notes of large size. The text content represent the numeric percentage. A value of 100 would be identical to the size of a regular note as defined by the music font.
    """
    
    TYPE = XSDComplexTypeNoteSize
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="note-size" type="note-size" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLDistance(XMLElement):
    """
    The distance element represents standard distances between notation elements in tenths. The type attribute defines what type of distance is being defined. Valid values include hyphen (for hyphens in lyrics) and beam.
    """
    
    TYPE = XSDComplexTypeDistance
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="distance" type="distance" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLGlyph(XMLElement):
    """
    The glyph element represents what SMuFL glyph should be used for different variations of symbols that are semantically identical. The type attribute specifies what type of glyph is being defined. The element value specifies what SMuFL glyph to use, including recommended stylistic alternates. The SMuFL glyph name should match the type. For instance, a type of quarter-rest would use values restQuarter, restQuarterOld, or restQuarterZ. A type of g-clef-ottava-bassa would use values gClef8vb, gClef8vbOld, or gClef8vbCClef. A type of octave-shift-up-8 would use values ottava, ottavaBassa, ottavaBassaBa, ottavaBassaVb, or octaveBassa.
    """
    
    TYPE = XSDComplexTypeGlyph
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="glyph" type="glyph" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLOtherAppearance(XMLElement):
    """
    The other-appearance type is used to define any graphical settings not yet in the current version of the MusicXML format. This allows extended representation, though without application interoperability.
    """
    
    TYPE = XSDComplexTypeOtherAppearance
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-appearance" type="other-appearance" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLMeasureDistance(XMLElement):
    """
    The measure-distance element specifies the horizontal distance from the previous measure. This value is only used for systems where there is horizontal whitespace in the middle of a system, as in systems with codas. To specify the measure width, use the width attribute of the measure element.
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="measure-distance" type="tenths" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The measure-distance element specifies the horizontal distance from the previous measure. This value is only used for systems where there is horizontal whitespace in the middle of a system, as in systems with codas. To specify the measure width, use the width attribute of the measure element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPageHeight(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="page-height" type="tenths" />
"""
                                     ))


class XMLPageWidth(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="page-width" type="tenths" />
"""
                                     ))


class XMLPageMargins(XMLElement):
    """
    Page margins are specified either for both even and odd pages, or via separate odd and even page number values. The type attribute is not needed when used as part of a print element. If omitted when the page-margins type is used in the defaults element, "both" is the default value.\n
    XSD structure:\n
    Group\@name=all-margins\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Group\@name=left-right-margins\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=left-margin\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=right-margin\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=top-margin\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=bottom-margin\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePageMargins
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="page-margins" type="page-margins" minOccurs="0" maxOccurs="2" />
"""
                                     ))


class XMLMillimeters(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeMillimeters
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="millimeters" type="millimeters" />
"""
                                     ))


class XMLTenths(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tenths" type="tenths" />
"""
                                     ))


class XMLStaffDistance(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-distance" type="tenths" minOccurs="0" />
"""
                                     ))


class XMLLeftDivider(XMLElement):
    """
    The empty-print-style-align-object type represents an empty element with print-object and print-style-align attribute groups.
    """
    
    TYPE = XSDComplexTypeEmptyPrintObjectStyleAlign
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="left-divider" type="empty-print-object-style-align" />
"""
                                     ))


class XMLRightDivider(XMLElement):
    """
    The empty-print-style-align-object type represents an empty element with print-object and print-style-align attribute groups.
    """
    
    TYPE = XSDComplexTypeEmptyPrintObjectStyleAlign
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="right-divider" type="empty-print-object-style-align" />
"""
                                     ))


class XMLSystemMargins(XMLElement):
    """
    System margins are relative to the page margins. Positive values indent and negative values reduce the margin size.\n
    XSD structure:\n
    Group\@name=left-right-margins\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=left-margin\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=right-margin\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeSystemMargins
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="system-margins" type="system-margins" minOccurs="0" />
"""
                                     ))


class XMLSystemDistance(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="system-distance" type="tenths" minOccurs="0" />
"""
                                     ))


class XMLTopSystemDistance(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="top-system-distance" type="tenths" minOccurs="0" />
"""
                                     ))


class XMLSystemDividers(XMLElement):
    """
    The system-dividers element indicates the presence or absence of system dividers (also known as system separation marks) between systems displayed on the same page. Dividers on the left and right side of the page are controlled by the left-divider and right-divider elements respectively. The default vertical position is half the system-distance value from the top of the system that is below the divider. The default horizontal position is the left and right system margin, respectively.
    
    When used in the print element, the system-dividers element affects the dividers that would appear between the current system and the previous system.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=left-divider\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=right-divider\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeSystemDividers
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="system-dividers" type="system-dividers" minOccurs="0" />
"""
                                     ))


class XMLAccent(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accent" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The accent element indicates a regular horizontal accent mark.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStrongAccent(XMLElement):
    """
    The strong-accent type indicates a vertical accent mark. The type attribute indicates if the point of the accent is down or up.
    """
    
    TYPE = XSDComplexTypeStrongAccent
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="strong-accent" type="strong-accent">
    <xs:annotation>
        <xs:documentation>The strong-accent element indicates a vertical accent mark.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStaccato(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staccato" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The staccato element is used for a dot articulation, as opposed to a stroke or a wedge.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTenuto(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tenuto" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The tenuto element indicates a tenuto line symbol.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDetachedLegato(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="detached-legato" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The detached-legato element indicates the combination of a tenuto line and staccato dot symbol.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStaccatissimo(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staccatissimo" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The staccatissimo element is used for a wedge articulation, as opposed to a dot or a stroke.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSpiccato(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="spiccato" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The spiccato element is used for a stroke articulation, as opposed to a dot or a wedge.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLScoop(XMLElement):
    """
    The empty-line type represents an empty element with line-shape, line-type, line-length, dashed-formatting, print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyLine
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="scoop" type="empty-line">
    <xs:annotation>
        <xs:documentation>The scoop element is an indeterminate slide attached to a single note. The scoop appears before the main note and comes from below the main pitch.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPlop(XMLElement):
    """
    The empty-line type represents an empty element with line-shape, line-type, line-length, dashed-formatting, print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyLine
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="plop" type="empty-line">
    <xs:annotation>
        <xs:documentation>The plop element is an indeterminate slide attached to a single note. The plop appears before the main note and comes from above the main pitch.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDoit(XMLElement):
    """
    The empty-line type represents an empty element with line-shape, line-type, line-length, dashed-formatting, print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyLine
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="doit" type="empty-line">
    <xs:annotation>
        <xs:documentation>The doit element is an indeterminate slide attached to a single note. The doit appears after the main note and goes above the main pitch.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLFalloff(XMLElement):
    """
    The empty-line type represents an empty element with line-shape, line-type, line-length, dashed-formatting, print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyLine
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="falloff" type="empty-line">
    <xs:annotation>
        <xs:documentation>The falloff element is an indeterminate slide attached to a single note. The falloff appears after the main note and goes below the main pitch.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBreathMark(XMLElement):
    """
    The breath-mark element indicates a place to take a breath.
    """
    
    TYPE = XSDComplexTypeBreathMark
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="breath-mark" type="breath-mark" />
"""
                                     ))


class XMLCaesura(XMLElement):
    """
    The caesura element indicates a slight pause. It is notated using a "railroad tracks" symbol or other variations specified in the element content.
    """
    
    TYPE = XSDComplexTypeCaesura
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="caesura" type="caesura" />
"""
                                     ))


class XMLStress(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="stress" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The stress element indicates a stressed note.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLUnstress(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="unstress" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The unstress element indicates an unstressed note. It is often notated using a u-shaped symbol.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSoftAccent(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="soft-accent" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The soft-accent element indicates a soft accent that is not as heavy as a normal accent. It is often notated as &lt;&gt;. It can be combined with other articulations to implement the first eight symbols in the SMuFL Articulation supplement range.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLOtherArticulation(XMLElement):
    """
    The other-placement-text type represents a text element with print-style, placement, and smufl attribute groups. This type is used by MusicXML notation extension elements to allow specification of specific SMuFL glyphs without needed to add every glyph as a MusicXML element.
    """
    
    TYPE = XSDComplexTypeOtherPlacementText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-articulation" type="other-placement-text">
    <xs:annotation>
        <xs:documentation>The other-articulation element is used to define any articulations not yet in the MusicXML format. The smufl attribute can be used to specify a particular articulation, allowing application interoperability without requiring every SMuFL articulation to have a MusicXML element equivalent. Using the other-articulation element without the smufl attribute allows for extended representation, though without application interoperability.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLArrowDirection(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeArrowDirection
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="arrow-direction" type="arrow-direction" />
"""
                                     ))


class XMLArrowStyle(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeArrowStyle
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="arrow-style" type="arrow-style" minOccurs="0" />
"""
                                     ))


class XMLArrowhead(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="arrowhead" type="empty" minOccurs="0" />
"""
                                     ))


class XMLCircularArrow(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeCircularArrow
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="circular-arrow" type="circular-arrow" />
"""
                                     ))


class XMLBendAlter(XMLElement):
    """
    The bend-alter element indicates the number of semitones in the bend, similar to the alter element. As with the alter element, numbers like 0.5 can be used to indicate microtones. Negative values indicate pre-bends or releases. The pre-bend and release elements are used to distinguish what is intended. Because the bend-alter element represents the number of steps in the bend, a release after a bend has a negative bend-alter value, not a zero value.
    """
    
    TYPE = XSDSimpleTypeSemitones
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bend-alter" type="semitones">
    <xs:annotation>
        <xs:documentation>The bend-alter element indicates the number of semitones in the bend, similar to the alter element. As with the alter element, numbers like 0.5 can be used to indicate microtones. Negative values indicate pre-bends or releases. The pre-bend and release elements are used to distinguish what is intended. Because the bend-alter element represents the number of steps in the bend, a release after a bend has a negative bend-alter value, not a zero value.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPreBend(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pre-bend" type="empty">
    <xs:annotation>
        <xs:documentation>The pre-bend element indicates that a bend is a pre-bend rather than a normal bend or a release.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLRelease(XMLElement):
    """
    The release type indicates that a bend is a release rather than a normal bend or pre-bend. The offset attribute specifies where the release starts in terms of divisions relative to the current note. The first-beat and last-beat attributes of the parent bend element are relative to the original note position, not this offset value.
    """
    
    TYPE = XSDComplexTypeRelease
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="release" type="release" />
"""
                                     ))


class XMLWithBar(XMLElement):
    """
    The placement-text type represents a text element with print-style and placement attribute groups.
    """
    
    TYPE = XSDComplexTypePlacementText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="with-bar" type="placement-text" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The with-bar element indicates that the bend is to be done at the bridge with a whammy or vibrato bar. The content of the element indicates how this should be notated. Content values of "scoop" and "dip" refer to the SMuFL guitarVibratoBarScoop and guitarVibratoBarDip glyphs.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPrefix(XMLElement):
    """
    The style-text type represents a text element with a print-style attribute group.
    """
    
    TYPE = XSDComplexTypeStyleText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="prefix" type="style-text" minOccurs="0">
    <xs:annotation>
        <xs:documentation>Values for the prefix element include plus and the accidental values sharp, flat, natural, double-sharp, flat-flat, and sharp-sharp. The prefix element may contain additional values for symbols specific to particular figured bass styles.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLFigureNumber(XMLElement):
    """
    The style-text type represents a text element with a print-style attribute group.
    """
    
    TYPE = XSDComplexTypeStyleText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="figure-number" type="style-text" minOccurs="0">
    <xs:annotation>
        <xs:documentation>A figure-number is a number. Overstrikes of the figure number are represented in the suffix element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSuffix(XMLElement):
    """
    The style-text type represents a text element with a print-style attribute group.
    """
    
    TYPE = XSDComplexTypeStyleText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="suffix" type="style-text" minOccurs="0">
    <xs:annotation>
        <xs:documentation>Values for the suffix element include plus and the accidental values sharp, flat, natural, double-sharp, flat-flat, and sharp-sharp. Suffixes include both symbols that come after the figure number and those that overstrike the figure number. The suffix values slash, back-slash, and vertical are used for slashed numbers indicating chromatic alteration. The orientation and display of the slash usually depends on the figure number. The suffix element may contain additional values for symbols specific to particular figured bass styles.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLExtend(XMLElement):
    """
    The extend type represents lyric word extension / melisma lines as well as figured bass extensions. The optional type and position attributes are added in Version 3.0 to provide better formatting control.
    """
    
    TYPE = XSDComplexTypeExtend
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="extend" type="extend" minOccurs="0" />
"""
                                     ))


class XMLFigure(XMLElement):
    """
    The figure type represents a single figure within a figured-bass element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=prefix\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=figure-number\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=suffix\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=extend\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeFigure
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="figure" type="figure" maxOccurs="unbounded" />
"""
                                     ))


class XMLHarmonClosed(XMLElement):
    """
    The harmon-closed type represents whether the harmon mute is closed, open, or half-open. The optional location attribute indicates which portion of the symbol is filled in when the element value is half.
    """
    
    TYPE = XSDComplexTypeHarmonClosed
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="harmon-closed" type="harmon-closed" />
"""
                                     ))


class XMLNatural(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="natural" type="empty">
    <xs:annotation>
        <xs:documentation>The natural element indicates that this is a natural harmonic. These are usually notated at base pitch rather than sounding pitch.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLArtificial(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="artificial" type="empty">
    <xs:annotation>
        <xs:documentation>The artificial element indicates that this is an artificial harmonic.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBasePitch(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="base-pitch" type="empty">
    <xs:annotation>
        <xs:documentation>The base pitch is the pitch at which the string is played before touching to create the harmonic.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTouchingPitch(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="touching-pitch" type="empty">
    <xs:annotation>
        <xs:documentation>The touching-pitch is the pitch at which the string is touched lightly to produce the harmonic.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSoundingPitch(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sounding-pitch" type="empty">
    <xs:annotation>
        <xs:documentation>The sounding-pitch is the pitch which is heard when playing the harmonic.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHoleType(XMLElement):
    """
    The content of the optional hole-type element indicates what the hole symbol represents in terms of instrument fingering or other techniques.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="hole-type" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The content of the optional hole-type element indicates what the hole symbol represents in terms of instrument fingering or other techniques.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHoleClosed(XMLElement):
    """
    The hole-closed type represents whether the hole is closed, open, or half-open. The optional location attribute indicates which portion of the hole is filled in when the element value is half.
    """
    
    TYPE = XSDComplexTypeHoleClosed
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="hole-closed" type="hole-closed" />
"""
                                     ))


class XMLHoleShape(XMLElement):
    """
    The optional hole-shape element indicates the shape of the hole symbol; the default is a circle.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="hole-shape" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The optional hole-shape element indicates the shape of the hole symbol; the default is a circle.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLAssess(XMLElement):
    """
    By default, an assessment application should assess all notes without a cue child element, and not assess any note with a cue child element. The assess type allows this default assessment to be overridden for individual notes. The optional player and time-only attributes restrict the type to apply to a single player or set of times through a repeated section, respectively. If missing, the type applies to all players or all times through the repeated section, respectively. The player attribute references the id attribute of a player element defined within the matching score-part.
    """
    
    TYPE = XSDComplexTypeAssess
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="assess" type="assess" />
"""
                                     ))


class XMLWait(XMLElement):
    """
    The wait type specifies a point where the accompaniment should wait for a performer event before continuing. This typically happens at the start of new sections or after a held note or indeterminate music. These waiting points cannot always be inferred reliably from the contents of the displayed score. The optional player and time-only attributes restrict the type to apply to a single player or set of times through a repeated section, respectively.
    """
    
    TYPE = XSDComplexTypeWait
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="wait" type="wait" />
"""
                                     ))


class XMLOtherListen(XMLElement):
    """
    The other-listening type represents other types of listening control and interaction. The required type attribute indicates the type of listening to which the element content applies. The optional player and time-only attributes restrict the element to apply to a single player or set of times through a repeated section, respectively.
    """
    
    TYPE = XSDComplexTypeOtherListening
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-listen" type="other-listening" />
"""
                                     ))


class XMLSyllabic(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeSyllabic
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="syllabic" type="syllabic" minOccurs="0" />
"""
                                     ))


class XMLText(XMLElement):
    """
    The text-element-data type represents a syllable or portion of a syllable for lyric text underlay. A hyphen in the string content should only be used for an actual hyphenated word. Language names for text elements come from ISO 639, with optional country subcodes from ISO 3166.
    """
    
    TYPE = XSDComplexTypeTextElementData
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="text" type="text-element-data" />
"""
                                     ))


class XMLElision(XMLElement):
    """
    The elision type represents an elision between lyric syllables. The text content specifies the symbol used to display the elision. Common values are a no-break space (Unicode 00A0), an underscore (Unicode 005F), or an undertie (Unicode 203F). If the text content is empty, the smufl attribute is used to specify the symbol to use. Its value is a SMuFL canonical glyph name that starts with lyrics. The SMuFL attribute is ignored if the elision glyph is already specified by the text content. If neither text content nor a smufl attribute are present, the elision glyph is application-specific.
    """
    
    TYPE = XSDComplexTypeElision
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="elision" type="elision" />
"""
                                     ))


class XMLLaughing(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="laughing" type="empty">
    <xs:annotation>
        <xs:documentation>The laughing element represents a laughing voice.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHumming(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="humming" type="empty">
    <xs:annotation>
        <xs:documentation>The humming element represents a humming voice.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLEndLine(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="end-line" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The end-line element comes from RP-017 for Standard MIDI File Lyric meta-events. It facilitates lyric display for Karaoke and similar applications.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLEndParagraph(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="end-paragraph" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The end-paragraph element comes from RP-017 for Standard MIDI File Lyric meta-events. It facilitates lyric display for Karaoke and similar applications.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTied(XMLElement):
    """
    The tied element represents the notated tie. The tie element represents the tie sound.
    
    The number attribute is rarely needed to disambiguate ties, since note pitches will usually suffice. The attribute is implied rather than defaulting to 1 as with most elements. It is available for use in more complex tied notation situations.
    
    Ties that join two notes of the same pitch together should be represented with a tied element on the first note with type="start" and a tied element on the second note with type="stop".  This can also be done if the two notes being tied are enharmonically equivalent, but have different step values. It is not recommended to use tied elements to join two notes with enharmonically inequivalent pitches.
    
    Ties that indicate that an instrument should be undamped are specified with a single tied element with type="let-ring".
    
    Ties that are visually attached to only one note, other than undamped ties, should be specified with two tied elements on the same note, first type="start" then type="stop". This can be used to represent ties into or out of repeated sections or codas.
    """
    
    TYPE = XSDComplexTypeTied
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tied" type="tied" />
"""
                                     ))


class XMLSlur(XMLElement):
    """
    Slur types are empty. Most slurs are represented with two elements: one with a start type, and one with a stop type. Slurs can add more elements using a continue type. This is typically used to specify the formatting of cross-system slurs, or to specify the shape of very complex slurs.
    """
    
    TYPE = XSDComplexTypeSlur
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="slur" type="slur" />
"""
                                     ))


class XMLTuplet(XMLElement):
    """
    A tuplet element is present when a tuplet is to be displayed graphically, in addition to the sound data provided by the time-modification elements. The number attribute is used to distinguish nested tuplets. The bracket attribute is used to indicate the presence of a bracket. If unspecified, the results are implementation-dependent. The line-shape attribute is used to specify whether the bracket is straight or in the older curved or slurred style. It is straight by default.
    
    Whereas a time-modification element shows how the cumulative, sounding effect of tuplets and double-note tremolos compare to the written note type, the tuplet element describes how this is displayed. The tuplet element also provides more detailed representation information than the time-modification element, and is needed to represent nested tuplets and other complex tuplets accurately.
    
    The show-number attribute is used to display either the number of actual notes, the number of both actual and normal notes, or neither. It is actual by default. The show-type attribute is used to display either the actual type, both the actual and normal types, or neither. It is none by default.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=tuplet-actual\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=tuplet-normal\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeTuplet
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuplet" type="tuplet" />
"""
                                     ))


class XMLGlissando(XMLElement):
    """
    Glissando and slide types both indicate rapidly moving from one pitch to the other so that individual notes are not discerned. A glissando sounds the distinct notes in between the two pitches and defaults to a wavy line. The optional text is printed alongside the line.
    """
    
    TYPE = XSDComplexTypeGlissando
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="glissando" type="glissando" />
"""
                                     ))


class XMLSlide(XMLElement):
    """
    Glissando and slide types both indicate rapidly moving from one pitch to the other so that individual notes are not discerned. A slide is continuous between the two pitches and defaults to a solid line. The optional text for a is printed alongside the line.
    """
    
    TYPE = XSDComplexTypeSlide
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="slide" type="slide" />
"""
                                     ))


class XMLOrnaments(XMLElement):
    """
    Ornaments can be any of several types, followed optionally by accidentals. The accidental-mark element's content is represented the same as an accidental element, but with a different name to reflect the different musical meaning.\n
    XSD structure:\n
    Sequence\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=trill-mark\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=turn\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=delayed-turn\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=inverted-turn\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=delayed-inverted-turn\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=vertical-turn\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=inverted-vertical-turn\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=shake\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=wavy-line\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=mordent\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=inverted-mordent\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=schleifer\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=tremolo\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=haydn\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=other-ornament\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=accidental-mark\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeOrnaments
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ornaments" type="ornaments" />
"""
                                     ))


class XMLTechnical(XMLElement):
    """
    Technical indications give performance information for individual instruments.\n
    XSD structure:\n
    Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=up-bow\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=down-bow\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=harmonic\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=open-string\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=thumb-position\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fingering\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pluck\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=double-tongue\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=triple-tongue\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=stopped\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=snap-pizzicato\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fret\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=string\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=hammer-on\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=pull-off\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=bend\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=tap\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=heel\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=toe\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=fingernails\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=hole\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=arrow\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=handbell\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=brass-bend\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=flip\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=smear\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=open\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=half-muted\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=harmon-mute\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=golpe\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=other-technical\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeTechnical
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="technical" type="technical" />
"""
                                     ))


class XMLArticulations(XMLElement):
    """
    Articulations and accents are grouped together here.\n
    XSD structure:\n
    Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=accent\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=strong-accent\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=staccato\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=tenuto\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=detached-legato\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=staccatissimo\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=spiccato\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=scoop\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=plop\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=doit\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=falloff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=breath-mark\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=caesura\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=stress\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=unstress\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=soft-accent\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=other-articulation\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeArticulations
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="articulations" type="articulations" />
"""
                                     ))


class XMLArpeggiate(XMLElement):
    """
    The arpeggiate type indicates that this note is part of an arpeggiated chord. The number attribute can be used to distinguish between two simultaneous chords arpeggiated separately (different numbers) or together (same number). The direction attribute is used if there is an arrow on the arpeggio sign. By default, arpeggios go from the lowest to highest note.  The length of the sign can be determined from the position attributes for the arpeggiate elements used with the top and bottom notes of the arpeggiated chord. If the unbroken attribute is set to yes, it indicates that the arpeggio continues onto another staff within the part. This serves as a hint to applications and is not required for cross-staff arpeggios.
    """
    
    TYPE = XSDComplexTypeArpeggiate
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="arpeggiate" type="arpeggiate" />
"""
                                     ))


class XMLNonArpeggiate(XMLElement):
    """
    The non-arpeggiate type indicates that this note is at the top or bottom of a bracket indicating to not arpeggiate these notes. Since this does not involve playback, it is only used on the top or bottom notes, not on each note as for the arpeggiate type.
    """
    
    TYPE = XSDComplexTypeNonArpeggiate
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="non-arpeggiate" type="non-arpeggiate" />
"""
                                     ))


class XMLAccidentalMark(XMLElement):
    """
    An accidental-mark can be used as a separate notation or as part of an ornament. When used in an ornament, position and placement are relative to the ornament, not relative to the note.
    """
    
    TYPE = XSDComplexTypeAccidentalMark
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accidental-mark" type="accidental-mark" />
"""
                                     ))


class XMLOtherNotation(XMLElement):
    """
    The other-notation type is used to define any notations not yet in the MusicXML format. It handles notations where more specific extension elements such as other-dynamics and other-technical are not appropriate. The smufl attribute can be used to specify a particular notation, allowing application interoperability without requiring every SMuFL glyph to have a MusicXML element equivalent. Using the other-notation type without the smufl attribute allows for extended representation, though without application interoperability.
    """
    
    TYPE = XSDComplexTypeOtherNotation
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-notation" type="other-notation" />
"""
                                     ))


class XMLGrace(XMLElement):
    """
    The grace type indicates the presence of a grace note. The slash attribute for a grace note is yes for slashed grace notes. The steal-time-previous attribute indicates the percentage of time to steal from the previous note for the grace note. The steal-time-following attribute indicates the percentage of time to steal from the following note for the grace note, as for appoggiaturas. The make-time attribute indicates to make time, not steal time; the units are in real-time divisions for the grace note.
    """
    
    TYPE = XSDComplexTypeGrace
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="grace" type="grace" />
"""
                                     ))


class XMLTie(XMLElement):
    """
    The tie element indicates that a tie begins or ends with this note. If the tie element applies only particular times through a repeat, the time-only attribute indicates which times to apply it. The tie element indicates sound; the tied element indicates notation.
    """
    
    TYPE = XSDComplexTypeTie
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tie" type="tie" minOccurs="0" maxOccurs="2" />
"""
                                     ))


class XMLCue(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="cue" type="empty" />
"""
                                     ))


class XMLInstrument(XMLElement):
    """
    The instrument type distinguishes between score-instrument elements in a score-part. The id attribute is an IDREF back to the score-instrument ID. If multiple score-instruments are specified in a score-part, there should be an instrument element for each note in the part. Notes that are shared between multiple score-instruments can have more than one instrument element.
    """
    
    TYPE = XSDComplexTypeInstrument
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="instrument" type="instrument" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLType(XMLElement):
    """
    The note-type type indicates the graphic note type. Values range from 1024th to maxima. The size attribute indicates full, cue, grace-cue, or large size. The default is full for regular notes, grace-cue for notes that contain both grace and cue elements, and cue for notes that contain either a cue or a grace element, but not both.
    """
    
    TYPE = XSDComplexTypeNoteType
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="type" type="note-type" minOccurs="0" />
"""
                                     ))


class XMLDot(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="dot" type="empty-placement" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>One dot element is used for each dot of prolongation. The placement attribute is used to specify whether the dot should appear above or below the staff line. It is ignored for notes that appear on a staff space.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLAccidental(XMLElement):
    """
    The accidental type represents actual notated accidentals. Editorial and cautionary indications are indicated by attributes. Values for these attributes are "no" if not present. Specific graphic display such as parentheses, brackets, and size are controlled by the level-display attribute group.
    """
    
    TYPE = XSDComplexTypeAccidental
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="accidental" type="accidental" minOccurs="0" />
"""
                                     ))


class XMLTimeModification(XMLElement):
    """
    Time modification indicates tuplets, double-note tremolos, and other durational changes. A time-modification element shows how the cumulative, sounding effect of tuplets and double-note tremolos compare to the written note type represented by the type and dot elements. Nested tuplets and other notations that use more detailed information need both the time-modification and tuplet elements to be represented accurately.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=actual-notes\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=normal-notes\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=normal-type\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=normal-dot\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeTimeModification
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="time-modification" type="time-modification" minOccurs="0" />
"""
                                     ))


class XMLStem(XMLElement):
    """
    Stems can be down, up, none, or double. For down and up stems, the position attributes can be used to specify stem length. The relative values specify the end of the stem relative to the program default. Default values specify an absolute end stem position. Negative values of relative-y that would flip a stem instead of shortening it are ignored. A stem element associated with a rest refers to a stemlet.
    """
    
    TYPE = XSDComplexTypeStem
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="stem" type="stem" minOccurs="0" />
"""
                                     ))


class XMLNotehead(XMLElement):
    """
    The notehead type indicates shapes other than the open and closed ovals associated with note durations. 
    
    The smufl attribute can be used to specify a particular notehead, allowing application interoperability without requiring every SMuFL glyph to have a MusicXML element equivalent. This attribute can be used either with the "other" value, or to refine a specific notehead value such as "cluster". Noteheads in the SMuFL Note name noteheads and Note name noteheads supplement ranges (U+E150–U+E1AF and U+EEE0–U+EEFF) should not use the smufl attribute or the "other" value, but instead use the notehead-text element.
    
    For the enclosed shapes, the default is to be hollow for half notes and longer, and filled otherwise. The filled attribute can be set to change this if needed.
    
    If the parentheses attribute is set to yes, the notehead is parenthesized. It is no by default.
    """
    
    TYPE = XSDComplexTypeNotehead
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="notehead" type="notehead" minOccurs="0" />
"""
                                     ))


class XMLNoteheadText(XMLElement):
    """
    The notehead-text type represents text that is displayed inside a notehead, as is done in some educational music. It is not needed for the numbers used in tablature or jianpu notation. The presence of a TAB or jianpu clefs is sufficient to indicate that numbers are used. The display-text and accidental-text elements allow display of fully formatted text and accidentals.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=display-text\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=accidental-text\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNoteheadText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="notehead-text" type="notehead-text" minOccurs="0" />
"""
                                     ))


class XMLBeam(XMLElement):
    """
    Beam values include begin, continue, end, forward hook, and backward hook. Up to eight concurrent beams are available to cover up to 1024th notes. Each beam in a note is represented with a separate beam element, starting with the eighth note beam using a number attribute of 1.
    
    Note that the beam number does not distinguish sets of beams that overlap, as it does for slur and other elements. Beaming groups are distinguished by being in different voices and/or the presence or absence of grace and cue elements.
    
    Beams that have a begin value can also have a fan attribute to indicate accelerandos and ritardandos using fanned beams. The fan attribute may also be used with a continue value if the fanning direction changes on that note. The value is "none" if not specified.
    
    The repeater attribute has been deprecated in MusicXML 3.0. Formerly used for tremolos, it needs to be specified with a "yes" value for each beam using it.
    """
    
    TYPE = XSDComplexTypeBeam
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beam" type="beam" minOccurs="0" maxOccurs="8" />
"""
                                     ))


class XMLNotations(XMLElement):
    """
    Notations refer to musical notations, not XML notations. Multiple notations are allowed in order to represent multiple editorial levels. The print-object attribute, added in Version 3.0, allows notations to represent details of performance technique, such as fingerings, without having them appear in the score.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=tied\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=slur\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=tuplet\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=glissando\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=slide\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=ornaments\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=technical\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=articulations\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=dynamics\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=fermata\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=arpeggiate\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=non-arpeggiate\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=accidental-mark\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=other-notation\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNotations
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="notations" type="notations" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLLyric(XMLElement):
    """
    The lyric type represents text underlays for lyrics. Two text elements that are not separated by an elision element are part of the same syllable, but may have different text formatting. The MusicXML XSD is more strict than the DTD in enforcing this by disallowing a second syllabic element unless preceded by an elision element. The lyric number indicates multiple lines, though a name can be used as well. Common name examples are verse and chorus.
    
    Justification is center by default; placement is below by default. Vertical alignment is to the baseline of the text and horizontal alignment matches justification. The print-object attribute can override a note's print-lyric attribute in cases where only some lyrics on a note are printed, as when lyrics for later verses are printed in a block of text rather than with each note. The time-only attribute precisely specifies which lyrics are to be sung which time through a repeated section.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=syllabic\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=text\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=elision\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=syllabic\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=text\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=extend\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=extend\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=laughing\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=humming\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=end-line\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=end-paragraph\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeLyric
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="lyric" type="lyric" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLListen(XMLElement):
    """
    The listen and listening types, new in Version 4.0, specify different ways that a score following or machine listening application can interact with a performer. The listen type handles interactions that are specific to a note. If multiple child elements of the same type are present, they should have distinct player and/or time-only attributes.\n
    XSD structure:\n
    Choice\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Element\@name=assess\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=wait\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=other-listen\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeListen
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="listen" type="listen" minOccurs="0" />
"""
                                     ))


class XMLTrillMark(XMLElement):
    """
    The empty-trill-sound type represents an empty element with print-style, placement, and trill-sound attributes.
    """
    
    TYPE = XSDComplexTypeEmptyTrillSound
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="trill-mark" type="empty-trill-sound">
    <xs:annotation>
        <xs:documentation>The trill-mark element represents the trill-mark symbol.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTurn(XMLElement):
    """
    The horizontal-turn type represents turn elements that are horizontal rather than vertical. These are empty elements with print-style, placement, trill-sound, and slash attributes. If the slash attribute is yes, then a vertical line is used to slash the turn. It is no if not specified.
    """
    
    TYPE = XSDComplexTypeHorizontalTurn
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="turn" type="horizontal-turn">
    <xs:annotation>
        <xs:documentation>The turn element is the normal turn shape which goes up then down.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDelayedTurn(XMLElement):
    """
    The horizontal-turn type represents turn elements that are horizontal rather than vertical. These are empty elements with print-style, placement, trill-sound, and slash attributes. If the slash attribute is yes, then a vertical line is used to slash the turn. It is no if not specified.
    """
    
    TYPE = XSDComplexTypeHorizontalTurn
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="delayed-turn" type="horizontal-turn">
    <xs:annotation>
        <xs:documentation>The delayed-turn element indicates a normal turn that is delayed until the end of the current note.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInvertedTurn(XMLElement):
    """
    The horizontal-turn type represents turn elements that are horizontal rather than vertical. These are empty elements with print-style, placement, trill-sound, and slash attributes. If the slash attribute is yes, then a vertical line is used to slash the turn. It is no if not specified.
    """
    
    TYPE = XSDComplexTypeHorizontalTurn
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="inverted-turn" type="horizontal-turn">
    <xs:annotation>
        <xs:documentation>The inverted-turn element has the shape which goes down and then up.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDelayedInvertedTurn(XMLElement):
    """
    The horizontal-turn type represents turn elements that are horizontal rather than vertical. These are empty elements with print-style, placement, trill-sound, and slash attributes. If the slash attribute is yes, then a vertical line is used to slash the turn. It is no if not specified.
    """
    
    TYPE = XSDComplexTypeHorizontalTurn
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="delayed-inverted-turn" type="horizontal-turn">
    <xs:annotation>
        <xs:documentation>The delayed-inverted-turn element indicates an inverted turn that is delayed until the end of the current note.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLVerticalTurn(XMLElement):
    """
    The empty-trill-sound type represents an empty element with print-style, placement, and trill-sound attributes.
    """
    
    TYPE = XSDComplexTypeEmptyTrillSound
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="vertical-turn" type="empty-trill-sound">
    <xs:annotation>
        <xs:documentation>The vertical-turn element has the turn symbol shape arranged vertically going from upper left to lower right.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInvertedVerticalTurn(XMLElement):
    """
    The empty-trill-sound type represents an empty element with print-style, placement, and trill-sound attributes.
    """
    
    TYPE = XSDComplexTypeEmptyTrillSound
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="inverted-vertical-turn" type="empty-trill-sound">
    <xs:annotation>
        <xs:documentation>The inverted-vertical-turn element has the turn symbol shape arranged vertically going from upper right to lower left.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLShake(XMLElement):
    """
    The empty-trill-sound type represents an empty element with print-style, placement, and trill-sound attributes.
    """
    
    TYPE = XSDComplexTypeEmptyTrillSound
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="shake" type="empty-trill-sound">
    <xs:annotation>
        <xs:documentation>The shake element has a similar appearance to an inverted-mordent element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMordent(XMLElement):
    """
    The mordent type is used for both represents the mordent sign with the vertical line and the inverted-mordent sign without the line. The long attribute is "no" by default. The approach and departure attributes are used for compound ornaments, indicating how the beginning and ending of the ornament look relative to the main part of the mordent.
    """
    
    TYPE = XSDComplexTypeMordent
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="mordent" type="mordent">
    <xs:annotation>
        <xs:documentation>The mordent element represents the sign with the vertical line. The choice of which mordent sign is inverted differs between MusicXML and SMuFL. The long attribute is "no" by default.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInvertedMordent(XMLElement):
    """
    The mordent type is used for both represents the mordent sign with the vertical line and the inverted-mordent sign without the line. The long attribute is "no" by default. The approach and departure attributes are used for compound ornaments, indicating how the beginning and ending of the ornament look relative to the main part of the mordent.
    """
    
    TYPE = XSDComplexTypeMordent
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="inverted-mordent" type="mordent">
    <xs:annotation>
        <xs:documentation>The inverted-mordent element represents the sign without the vertical line. The choice of which mordent is inverted differs between MusicXML and SMuFL. The long attribute is "no" by default.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSchleifer(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="schleifer" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The name for this ornament is based on the German, to avoid confusion with the more common slide element defined earlier.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTremolo(XMLElement):
    """
    The tremolo ornament can be used to indicate single-note, double-note, or unmeasured tremolos. Single-note tremolos use the single type, double-note tremolos use the start and stop types, and unmeasured tremolos use the unmeasured type. The default is "single" for compatibility with Version 1.1. The text of the element indicates the number of tremolo marks and is an integer from 0 to 8. Note that the number of attached beams is not included in this value, but is represented separately using the beam element. The value should be 0 for unmeasured tremolos.
    
    When using double-note tremolos, the duration of each note in the tremolo should correspond to half of the notated type value. A time-modification element should also be added with an actual-notes value of 2 and a normal-notes value of 1. If used within a tuplet, this 2/1 ratio should be multiplied by the existing tuplet ratio.
    
    The smufl attribute specifies the glyph to use from the SMuFL Tremolos range for an unmeasured tremolo. It is ignored for other tremolo types. The SMuFL buzzRoll glyph is used by default if the attribute is missing.
    
    Using repeater beams for indicating tremolos is deprecated as of MusicXML 3.0.
    """
    
    TYPE = XSDComplexTypeTremolo
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tremolo" type="tremolo" />
"""
                                     ))


class XMLHaydn(XMLElement):
    """
    The empty-trill-sound type represents an empty element with print-style, placement, and trill-sound attributes.
    """
    
    TYPE = XSDComplexTypeEmptyTrillSound
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="haydn" type="empty-trill-sound">
    <xs:annotation>
        <xs:documentation>The haydn element represents the Haydn ornament. This is defined in SMuFL as ornamentHaydn.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLOtherOrnament(XMLElement):
    """
    The other-placement-text type represents a text element with print-style, placement, and smufl attribute groups. This type is used by MusicXML notation extension elements to allow specification of specific SMuFL glyphs without needed to add every glyph as a MusicXML element.
    """
    
    TYPE = XSDComplexTypeOtherPlacementText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-ornament" type="other-placement-text">
    <xs:annotation>
        <xs:documentation>The other-ornament element is used to define any ornaments not yet in the MusicXML format. The smufl attribute can be used to specify a particular ornament, allowing application interoperability without requiring every SMuFL ornament to have a MusicXML element equivalent. Using the other-ornament element without the smufl attribute allows for extended representation, though without application interoperability.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStep(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeStep
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="step" type="step" />
"""
                                     ))


class XMLAlter(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeSemitones
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="alter" type="semitones" minOccurs="0" />
"""
                                     ))


class XMLOctave(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeOctave
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="octave" type="octave" />
"""
                                     ))


class XMLUpBow(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="up-bow" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The up-bow element represents the symbol that is used both for up-bowing on bowed instruments, and up-stroke on plucked instruments.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDownBow(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="down-bow" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The down-bow element represents the symbol that is used both for down-bowing on bowed instruments, and down-stroke on plucked instruments.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHarmonic(XMLElement):
    """
    The harmonic type indicates natural and artificial harmonics. Allowing the type of pitch to be specified, combined with controls for appearance/playback differences, allows both the notation and the sound to be represented. Artificial harmonics can add a notated touching pitch; artificial pinch harmonics will usually not notate a touching pitch. The attributes for the harmonic element refer to the use of the circular harmonic symbol, typically but not always used with natural harmonics.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=natural\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=artificial\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=base-pitch\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=touching-pitch\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=sounding-pitch\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeHarmonic
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="harmonic" type="harmonic" />
"""
                                     ))


class XMLOpenString(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="open-string" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The open-string element represents the zero-shaped open string symbol.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLThumbPosition(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="thumb-position" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The thumb-position element represents the thumb position symbol. This is a circle with a line, where the line does not come within the circle. It is distinct from the snap pizzicato symbol, where the line comes inside the circle.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPluck(XMLElement):
    """
    The placement-text type represents a text element with print-style and placement attribute groups.
    """
    
    TYPE = XSDComplexTypePlacementText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pluck" type="placement-text">
    <xs:annotation>
        <xs:documentation>The pluck element is used to specify the plucking fingering on a fretted instrument, where the fingering element refers to the fretting fingering. Typical values are p, i, m, a for pulgar/thumb, indicio/index, medio/middle, and anular/ring fingers.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDoubleTongue(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="double-tongue" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The double-tongue element represents the double tongue symbol (two dots arranged horizontally).</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTripleTongue(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="triple-tongue" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The triple-tongue element represents the triple tongue symbol (three dots arranged horizontally).</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLStopped(XMLElement):
    """
    The empty-placement-smufl type represents an empty element with print-style, placement, and smufl attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacementSmufl
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="stopped" type="empty-placement-smufl">
    <xs:annotation>
        <xs:documentation>The stopped element represents the stopped symbol, which looks like a plus sign. The smufl attribute distinguishes different SMuFL glyphs that have a similar appearance such as handbellsMalletBellSuspended and guitarClosePedal. If not present, the default glyph is brassMuteClosed.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSnapPizzicato(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="snap-pizzicato" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The snap-pizzicato element represents the snap pizzicato symbol. This is a circle with a line, where the line comes inside the circle. It is distinct from the thumb-position symbol, where the line does not come inside the circle.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHammerOn(XMLElement):
    """
    The hammer-on and pull-off elements are used in guitar and fretted instrument notation. Since a single slur can be marked over many notes, the hammer-on and pull-off elements are separate so the individual pair of notes can be specified. The element content can be used to specify how the hammer-on or pull-off should be notated. An empty element leaves this choice up to the application.
    """
    
    TYPE = XSDComplexTypeHammerOnPullOff
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="hammer-on" type="hammer-on-pull-off" />
"""
                                     ))


class XMLPullOff(XMLElement):
    """
    The hammer-on and pull-off elements are used in guitar and fretted instrument notation. Since a single slur can be marked over many notes, the hammer-on and pull-off elements are separate so the individual pair of notes can be specified. The element content can be used to specify how the hammer-on or pull-off should be notated. An empty element leaves this choice up to the application.
    """
    
    TYPE = XSDComplexTypeHammerOnPullOff
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pull-off" type="hammer-on-pull-off" />
"""
                                     ))


class XMLBend(XMLElement):
    """
    The bend type is used in guitar notation and tablature. A single note with a bend and release will contain two bend elements: the first to represent the bend and the second to represent the release. The shape attribute distinguishes between the angled bend symbols commonly used in standard notation and the curved bend symbols commonly used in both tablature and standard notation.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=bend-alter\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=pre-bend\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=release\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=with-bar\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeBend
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bend" type="bend" />
"""
                                     ))


class XMLTap(XMLElement):
    """
    The tap type indicates a tap on the fretboard. The text content allows specification of the notation; + and T are common choices. If the element is empty, the hand attribute is used to specify the symbol to use. The hand attribute is ignored if the tap glyph is already specified by the text content. If neither text content nor the hand attribute are present, the display is application-specific.
    """
    
    TYPE = XSDComplexTypeTap
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tap" type="tap" />
"""
                                     ))


class XMLHeel(XMLElement):
    """
    The heel and toe elements are used with organ pedals. The substitution value is "no" if the attribute is not present.
    """
    
    TYPE = XSDComplexTypeHeelToe
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="heel" type="heel-toe" />
"""
                                     ))


class XMLToe(XMLElement):
    """
    The heel and toe elements are used with organ pedals. The substitution value is "no" if the attribute is not present.
    """
    
    TYPE = XSDComplexTypeHeelToe
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="toe" type="heel-toe" />
"""
                                     ))


class XMLFingernails(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fingernails" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The fingernails element is used in notation for harp and other plucked string instruments.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHole(XMLElement):
    """
    The hole type represents the symbols used for woodwind and brass fingerings as well as other notations.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=hole-type\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=hole-closed\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=hole-shape\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeHole
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="hole" type="hole" />
"""
                                     ))


class XMLArrow(XMLElement):
    """
    The arrow element represents an arrow used for a musical technical indication. It can represent both Unicode and SMuFL arrows. The presence of an arrowhead element indicates that only the arrowhead is displayed, not the arrow stem. The smufl attribute distinguishes different SMuFL glyphs that have an arrow appearance such as arrowBlackUp, guitarStrumUp, or handbellsSwingUp. The specified glyph should match the descriptive representation.\n
    XSD structure:\n
    Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=arrow-direction\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=arrow-style\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=arrowhead\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=circular-arrow\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeArrow
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="arrow" type="arrow" />
"""
                                     ))


class XMLHandbell(XMLElement):
    """
    The handbell element represents notation for various techniques used in handbell and handchime music.
    """
    
    TYPE = XSDComplexTypeHandbell
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="handbell" type="handbell" />
"""
                                     ))


class XMLBrassBend(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="brass-bend" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The brass-bend element represents the u-shaped bend symbol used in brass notation, distinct from the bend element used in guitar music.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLFlip(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="flip" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The flip element represents the flip symbol used in brass notation.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSmear(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="smear" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The smear element represents the tilde-shaped smear symbol used in brass notation.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLOpen(XMLElement):
    """
    The empty-placement-smufl type represents an empty element with print-style, placement, and smufl attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacementSmufl
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="open" type="empty-placement-smufl">
    <xs:annotation>
        <xs:documentation>The open element represents the open symbol, which looks like a circle. The smufl attribute can be used to distinguish different SMuFL glyphs that have a similar appearance such as brassMuteOpen and guitarOpenPedal. If not present, the default glyph is brassMuteOpen.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHalfMuted(XMLElement):
    """
    The empty-placement-smufl type represents an empty element with print-style, placement, and smufl attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacementSmufl
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="half-muted" type="empty-placement-smufl">
    <xs:annotation>
        <xs:documentation>The half-muted element represents the half-muted symbol, which looks like a circle with a plus sign inside. The smufl attribute can be used to distinguish different SMuFL glyphs that have a similar appearance such as brassMuteHalfClosed and guitarHalfOpenPedal. If not present, the default glyph is brassMuteHalfClosed.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLHarmonMute(XMLElement):
    """
    The harmon-mute type represents the symbols used for harmon mutes in brass notation.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=harmon-closed\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeHarmonMute
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="harmon-mute" type="harmon-mute" />
"""
                                     ))


class XMLGolpe(XMLElement):
    """
    The empty-placement type represents an empty element with print-style and placement attributes.
    """
    
    TYPE = XSDComplexTypeEmptyPlacement
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="golpe" type="empty-placement">
    <xs:annotation>
        <xs:documentation>The golpe element represents the golpe symbol that is used for tapping the pick guard in guitar music.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLOtherTechnical(XMLElement):
    """
    The other-placement-text type represents a text element with print-style, placement, and smufl attribute groups. This type is used by MusicXML notation extension elements to allow specification of specific SMuFL glyphs without needed to add every glyph as a MusicXML element.
    """
    
    TYPE = XSDComplexTypeOtherPlacementText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="other-technical" type="other-placement-text">
    <xs:annotation>
        <xs:documentation>The other-technical element is used to define any technical indications not yet in the MusicXML format. The smufl attribute can be used to specify a particular glyph, allowing application interoperability without requiring every SMuFL technical indication to have a MusicXML element equivalent. Using the other-technical element without the smufl attribute allows for extended representation, though without application interoperability.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLActualNotes(XMLElement):
    """
    The actual-notes element describes how many notes are played in the time usually occupied by the number in the normal-notes element.
    """
    
    TYPE = XSDSimpleTypeNonNegativeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="actual-notes" type="xs:nonNegativeInteger">
    <xs:annotation>
        <xs:documentation>The actual-notes element describes how many notes are played in the time usually occupied by the number in the normal-notes element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLNormalNotes(XMLElement):
    """
    The normal-notes element describes how many notes are usually played in the time occupied by the number in the actual-notes element.
    """
    
    TYPE = XSDSimpleTypeNonNegativeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="normal-notes" type="xs:nonNegativeInteger">
    <xs:annotation>
        <xs:documentation>The normal-notes element describes how many notes are usually played in the time occupied by the number in the actual-notes element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLNormalType(XMLElement):
    """
    If the type associated with the number in the normal-notes element is different than the current note type (e.g., a quarter note within an eighth note triplet), then the normal-notes type (e.g. eighth) is specified in the normal-type and normal-dot elements.
    """
    
    TYPE = XSDSimpleTypeNoteTypeValue
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="normal-type" type="note-type-value">
    <xs:annotation>
        <xs:documentation>If the type associated with the number in the normal-notes element is different than the current note type (e.g., a quarter note within an eighth note triplet), then the normal-notes type (e.g. eighth) is specified in the normal-type and normal-dot elements.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLNormalDot(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="normal-dot" type="empty" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The normal-dot element is used to specify dotted normal tuplet types.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTupletActual(XMLElement):
    """
    The tuplet-portion type provides optional full control over tuplet specifications. It allows the number and note type (including dots) to be set for the actual and normal portions of a single tuplet. If any of these elements are absent, their values are based on the time-modification element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=tuplet-number\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=tuplet-type\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=tuplet-dot\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeTupletPortion
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuplet-actual" type="tuplet-portion" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The tuplet-actual element provide optional full control over how the actual part of the tuplet is displayed, including number and note type (with dots). If any of these elements are absent, their values are based on the time-modification element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTupletNormal(XMLElement):
    """
    The tuplet-portion type provides optional full control over tuplet specifications. It allows the number and note type (including dots) to be set for the actual and normal portions of a single tuplet. If any of these elements are absent, their values are based on the time-modification element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=tuplet-number\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=tuplet-type\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=tuplet-dot\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeTupletPortion
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuplet-normal" type="tuplet-portion" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The tuplet-normal element provide optional full control over how the normal part of the tuplet is displayed, including number and note type (with dots). If any of these elements are absent, their values are based on the time-modification element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTupletNumber(XMLElement):
    """
    The tuplet-number type indicates the number of notes for this portion of the tuplet.
    """
    
    TYPE = XSDComplexTypeTupletNumber
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuplet-number" type="tuplet-number" minOccurs="0" />
"""
                                     ))


class XMLTupletType(XMLElement):
    """
    The tuplet-type type indicates the graphical note type of the notes for this portion of the tuplet.
    """
    
    TYPE = XSDComplexTypeTupletType
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuplet-type" type="tuplet-type" minOccurs="0" />
"""
                                     ))


class XMLTupletDot(XMLElement):
    """
    The tuplet-dot type is used to specify dotted tuplet types.
    """
    
    TYPE = XSDComplexTypeTupletDot
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuplet-dot" type="tuplet-dot" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLCreditType(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="credit-type" type="xs:string" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLLink(XMLElement):
    """
    The link type serves as an outgoing simple XLink. If a relative link is used within a document that is part of a compressed MusicXML file, the link is relative to the root folder of the zip file.
    """
    
    TYPE = XSDComplexTypeLink
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="link" type="link" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLBookmark(XMLElement):
    """
    The bookmark type serves as a well-defined target for an incoming simple XLink.
    """
    
    TYPE = XSDComplexTypeBookmark
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bookmark" type="bookmark" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLCreditImage(XMLElement):
    """
    The image type is used to include graphical images in a score.
    """
    
    TYPE = XSDComplexTypeImage
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="credit-image" type="image" />
"""
                                     ))


class XMLCreditWords(XMLElement):
    """
    The formatted-text-id type represents a text element with text-formatting and id attributes.
    """
    
    TYPE = XSDComplexTypeFormattedTextId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="credit-words" type="formatted-text-id" />
"""
                                     ))


class XMLCreditSymbol(XMLElement):
    """
    The formatted-symbol-id type represents a SMuFL musical symbol element with formatting and id attributes.
    """
    
    TYPE = XSDComplexTypeFormattedSymbolId
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="credit-symbol" type="formatted-symbol-id" />
"""
                                     ))


class XMLScaling(XMLElement):
    """
    Margins, page sizes, and distances are all measured in tenths to keep MusicXML data in a consistent coordinate system as much as possible. The translation to absolute units is done with the scaling type, which specifies how many millimeters are equal to how many tenths. For a staff height of 7 mm, millimeters would be set to 7 while tenths is set to 40. The ability to set a formula rather than a single scaling factor helps avoid roundoff errors.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=millimeters\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=tenths\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeScaling
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="scaling" type="scaling" minOccurs="0" />
"""
                                     ))


class XMLConcertScore(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="concert-score" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The presence of a concert-score element indicates that a score is displayed in concert pitch. It is used for scores that contain parts for transposing instruments.

A document with a concert-score element may not contain any transpose elements that have non-zero values for either the diatonic or chromatic elements. Concert scores may include octave transpositions, so transpose elements with a double element or a non-zero octave-change element value are permitted.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLAppearance(XMLElement):
    """
    The appearance type controls general graphical settings for the music's final form appearance on a printed page of display. This includes support for line widths, definitions for note sizes, and standard distances between notation elements, plus an extension element for other aspects of appearance.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=line-width\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=note-size\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=distance\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=glyph\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=other-appearance\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeAppearance
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="appearance" type="appearance" minOccurs="0" />
"""
                                     ))


class XMLMusicFont(XMLElement):
    """
    The empty-font type represents an empty element with font attributes.
    """
    
    TYPE = XSDComplexTypeEmptyFont
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="music-font" type="empty-font" minOccurs="0" />
"""
                                     ))


class XMLWordFont(XMLElement):
    """
    The empty-font type represents an empty element with font attributes.
    """
    
    TYPE = XSDComplexTypeEmptyFont
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="word-font" type="empty-font" minOccurs="0" />
"""
                                     ))


class XMLLyricFont(XMLElement):
    """
    The lyric-font type specifies the default font for a particular name and number of lyric.
    """
    
    TYPE = XSDComplexTypeLyricFont
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="lyric-font" type="lyric-font" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLLyricLanguage(XMLElement):
    """
    The lyric-language type specifies the default language for a particular name and number of lyric.
    """
    
    TYPE = XSDComplexTypeLyricLanguage
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="lyric-language" type="lyric-language" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLGroupName(XMLElement):
    """
    The group-name type describes the name or abbreviation of a part-group element. Formatting attributes in the group-name type are deprecated in Version 2.0 in favor of the new group-name-display and group-abbreviation-display elements.
    """
    
    TYPE = XSDComplexTypeGroupName
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-name" type="group-name" minOccurs="0" />
"""
                                     ))


class XMLGroupNameDisplay(XMLElement):
    """
    The name-display type is used for exact formatting of multi-font text in part and group names to the left of the system. The print-object attribute can be used to determine what, if anything, is printed at the start of each system. Enclosure for the display-text element is none by default. Language for the display-text element is Italian ("it") by default.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=display-text\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=accidental-text\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNameDisplay
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-name-display" type="name-display" minOccurs="0">
    <xs:annotation>
        <xs:documentation>Formatting specified in the group-name-display element overrides formatting specified in the group-name element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLGroupAbbreviation(XMLElement):
    """
    The group-name type describes the name or abbreviation of a part-group element. Formatting attributes in the group-name type are deprecated in Version 2.0 in favor of the new group-name-display and group-abbreviation-display elements.
    """
    
    TYPE = XSDComplexTypeGroupName
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-abbreviation" type="group-name" minOccurs="0" />
"""
                                     ))


class XMLGroupAbbreviationDisplay(XMLElement):
    """
    The name-display type is used for exact formatting of multi-font text in part and group names to the left of the system. The print-object attribute can be used to determine what, if anything, is printed at the start of each system. Enclosure for the display-text element is none by default. Language for the display-text element is Italian ("it") by default.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=display-text\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=accidental-text\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNameDisplay
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-abbreviation-display" type="name-display" minOccurs="0">
    <xs:annotation>
        <xs:documentation>Formatting specified in the group-abbreviation-display element overrides formatting specified in the group-abbreviation element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLGroupSymbol(XMLElement):
    """
    The group-symbol type indicates how the symbol for a group is indicated in the score. It is none if not specified.
    """
    
    TYPE = XSDComplexTypeGroupSymbol
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-symbol" type="group-symbol" minOccurs="0" />
"""
                                     ))


class XMLGroupBarline(XMLElement):
    """
    The group-barline type indicates if the group should have common barlines.
    """
    
    TYPE = XSDComplexTypeGroupBarline
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-barline" type="group-barline" minOccurs="0" />
"""
                                     ))


class XMLGroupTime(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-time" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The group-time element indicates that the displayed time signatures should stretch across all parts and staves in the group.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInstrumentLink(XMLElement):
    """
    Multiple part-link elements can link a condensed part within a score file to multiple MusicXML parts files. For example, a "Clarinet 1 and 2" part in a score file could link to separate "Clarinet 1" and "Clarinet 2" part files. The instrument-link type distinguish which of the score-instruments within a score-part are in which part file. The instrument-link id attribute refers to a score-instrument id attribute.
    """
    
    TYPE = XSDComplexTypeInstrumentLink
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="instrument-link" type="instrument-link" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLGroupLink(XMLElement):
    """
    Multiple part-link elements can reference different types of linked documents, such as parts and condensed score. The optional group-link elements identify the groups used in the linked document. The content of a group-link element should match the content of a group element in the linked document.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group-link" type="xs:string" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>Multiple part-link elements can reference different types of linked documents, such as parts and condensed score. The optional group-link elements identify the groups used in the linked document. The content of a group-link element should match the content of a group element in the linked document.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPlayerName(XMLElement):
    """
    The player-name element is typically used within a software application, rather than appearing on the printed page of a score.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="player-name" type="xs:string">
    <xs:annotation>
        <xs:documentation>The player-name element is typically used within a software application, rather than appearing on the printed page of a score.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInstrumentName(XMLElement):
    """
    The instrument-name element is typically used within a software application, rather than appearing on the printed page of a score.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="instrument-name" type="xs:string">
    <xs:annotation>
        <xs:documentation>The instrument-name element is typically used within a software application, rather than appearing on the printed page of a score.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInstrumentAbbreviation(XMLElement):
    """
    The optional instrument-abbreviation element is typically used within a software application, rather than appearing on the printed page of a score.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="instrument-abbreviation" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The optional instrument-abbreviation element is typically used within a software application, rather than appearing on the printed page of a score.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLIdentification(XMLElement):
    """
    Identification contains basic metadata about the score. It includes information that may apply at a score-wide, movement-wide, or part-wide level. The creator, rights, source, and relation elements are based on Dublin Core.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=creator\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=rights\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=encoding\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=source\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=relation\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=miscellaneous\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeIdentification
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="identification" type="identification" minOccurs="0" />
"""
                                     ))


class XMLPartLink(XMLElement):
    """
    The part-link type allows MusicXML data for both score and parts to be contained within a single compressed MusicXML file. It links a score-part from a score document to MusicXML documents that contain parts data. In the case of a single compressed MusicXML file, the link href values are paths that are relative to the root folder of the zip file.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=instrument-link\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=group-link\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypePartLink
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-link" type="part-link" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLPartName(XMLElement):
    """
    The part-name type describes the name or abbreviation of a score-part element. Formatting attributes for the part-name element are deprecated in Version 2.0 in favor of the new part-name-display and part-abbreviation-display elements.
    """
    
    TYPE = XSDComplexTypePartName
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-name" type="part-name" />
"""
                                     ))


class XMLPartAbbreviation(XMLElement):
    """
    The part-name type describes the name or abbreviation of a score-part element. Formatting attributes for the part-name element are deprecated in Version 2.0 in favor of the new part-name-display and part-abbreviation-display elements.
    """
    
    TYPE = XSDComplexTypePartName
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-abbreviation" type="part-name" minOccurs="0" />
"""
                                     ))


class XMLGroup(XMLElement):
    """
    The group element allows the use of different versions of the part for different purposes. Typical values include score, parts, sound, and data. Ordering information can be derived from the ordering within a MusicXML score or opus.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="group" type="xs:string" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The group element allows the use of different versions of the part for different purposes. Typical values include score, parts, sound, and data. Ordering information can be derived from the ordering within a MusicXML score or opus.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLScoreInstrument(XMLElement):
    """
    The score-instrument type represents a single instrument within a score-part. As with the score-part type, each score-instrument has a required ID attribute, a name, and an optional abbreviation.
    
    A score-instrument type is also required if the score specifies MIDI 1.0 channels, banks, or programs. An initial midi-instrument assignment can also be made here. MusicXML software should be able to automatically assign reasonable channels and instruments without these elements in simple cases, such as where part names match General MIDI instrument names.
    
    The score-instrument element can also distinguish multiple instruments of the same type that are on the same part, such as Clarinet 1 and Clarinet 2 instruments within a Clarinets 1 and 2 part.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=instrument-name\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=instrument-abbreviation\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=virtual-instrument-data\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=instrument-sound\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Choice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=solo\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=ensemble\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=virtual-instrument\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeScoreInstrument
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="score-instrument" type="score-instrument" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLPlayer(XMLElement):
    """
    The player type allows for multiple players per score-part for use in listening applications. One player may play multiple instruments, while a single instrument may include multiple players in divisi sections.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=player-name\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePlayer
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="player" type="player" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLVirtualLibrary(XMLElement):
    """
    The virtual-library element indicates the virtual instrument library name.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="virtual-library" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The virtual-library element indicates the virtual instrument library name.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLVirtualName(XMLElement):
    """
    The virtual-name element indicates the library-specific name for the virtual instrument.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="virtual-name" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The virtual-name element indicates the library-specific name for the virtual instrument.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLWorkNumber(XMLElement):
    """
    The work-number element specifies the number of a work, such as its opus number.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="work-number" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The work-number element specifies the number of a work, such as its opus number.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLWorkTitle(XMLElement):
    """
    The work-title element specifies the title of a work, not including its opus or other work number.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="work-title" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The work-title element specifies the title of a work, not including its opus or other work number.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLOpus(XMLElement):
    """
    The opus type represents a link to a MusicXML opus document that composes multiple MusicXML scores into a collection.
    """
    
    TYPE = XSDComplexTypeOpus
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="opus" type="opus" minOccurs="0" />
"""
                                     ))


class XMLFootnote(XMLElement):
    """
    The formatted-text type represents a text element with text-formatting attributes.
    """
    
    TYPE = XSDComplexTypeFormattedText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="footnote" type="formatted-text" />
"""
                                     ))


class XMLLevel(XMLElement):
    """
    The level type is used to specify editorial information for different MusicXML elements. The content contains identifying and/or descriptive text about the editorial status of the parent element.
    
    If the reference attribute is yes, this indicates editorial information that is for display only and should not affect playback. For instance, a modern edition of older music may set reference="yes" on the attributes containing the music's original clef, key, and time signature. It is no if not specified.
    
    The type attribute indicates whether the editorial information applies to the start of a series of symbols, the end of a series of symbols, or a single symbol. It is single if not specified for compatibility with earlier MusicXML versions.
    """
    
    TYPE = XSDComplexTypeLevel
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="level" type="level" />
"""
                                     ))


class XMLStaff(XMLElement):
    """
    Staff assignment is only needed for music notated on multiple staves. Used by both notes and directions. Staff values are numbers, with 1 referring to the top-most staff in a part.
    """
    
    TYPE = XSDSimpleTypePositiveInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff" type="xs:positiveInteger">
    <xs:annotation>
        <xs:documentation>Staff assignment is only needed for music notated on multiple staves. Used by both notes and directions. Staff values are numbers, with 1 referring to the top-most staff in a part.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTuningStep(XMLElement):
    """
    The tuning-step element is represented like the step element, with a different name to reflect its different function in string tuning.
    """
    
    TYPE = XSDSimpleTypeStep
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuning-step" type="step">
    <xs:annotation>
        <xs:documentation>The tuning-step element is represented like the step element, with a different name to reflect its different function in string tuning.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTuningAlter(XMLElement):
    """
    The tuning-alter element is represented like the alter element, with a different name to reflect its different function in string tuning.
    """
    
    TYPE = XSDSimpleTypeSemitones
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuning-alter" type="semitones" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The tuning-alter element is represented like the alter element, with a different name to reflect its different function in string tuning.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLTuningOctave(XMLElement):
    """
    The tuning-octave element is represented like the octave element, with a different name to reflect its different function in string tuning.
    """
    
    TYPE = XSDSimpleTypeOctave
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="tuning-octave" type="octave">
    <xs:annotation>
        <xs:documentation>The tuning-octave element is represented like the octave element, with a different name to reflect its different function in string tuning.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLInstrumentSound(XMLElement):
    """
    The instrument-sound element describes the default timbre of the score-instrument. This description is independent of a particular virtual or MIDI instrument specification and allows playback to be shared more easily between applications and libraries.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="instrument-sound" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The instrument-sound element describes the default timbre of the score-instrument. This description is independent of a particular virtual or MIDI instrument specification and allows playback to be shared more easily between applications and libraries.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSolo(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="solo" type="empty">
    <xs:annotation>
        <xs:documentation>The solo element is present if performance is intended by a solo instrument.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLEnsemble(XMLElement):
    """
    The ensemble element is present if performance is intended by an ensemble such as an orchestral section. The text of the ensemble element contains the size of the section, or is empty if the ensemble size is not specified.
    """
    
    TYPE = XSDSimpleTypePositiveIntegerOrEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="ensemble" type="positive-integer-or-empty">
    <xs:annotation>
        <xs:documentation>The ensemble element is present if performance is intended by an ensemble such as an orchestral section. The text of the ensemble element contains the size of the section, or is empty if the ensemble size is not specified.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLVirtualInstrument(XMLElement):
    """
    The virtual-instrument element defines a specific virtual instrument used for an instrument sound.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=virtual-library\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=virtual-name\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeVirtualInstrument
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="virtual-instrument" type="virtual-instrument" minOccurs="0" />
"""
                                     ))


class XMLVoice(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="voice" type="xs:string" />
"""
                                     ))


class XMLSign(XMLElement):
    """
    The sign element represents the clef symbol.
    """
    
    TYPE = XSDSimpleTypeClefSign
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="sign" type="clef-sign">
    <xs:annotation>
        <xs:documentation>The sign element represents the clef symbol.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLLine(XMLElement):
    """
    Line numbers are counted from the bottom of the staff. They are only needed with the G, F, and C signs in order to position a pitch correctly on the staff. Standard values are 2 for the G sign (treble clef), 4 for the F sign (bass clef), and 3 for the C sign (alto clef). Line values can be used to specify positions outside the staff, such as a C clef positioned in the middle of a grand staff.
    """
    
    TYPE = XSDSimpleTypeStaffLinePosition
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="line" type="staff-line-position" minOccurs="0">
    <xs:annotation>
        <xs:documentation>Line numbers are counted from the bottom of the staff. They are only needed with the G, F, and C signs in order to position a pitch correctly on the staff. Standard values are 2 for the G sign (treble clef), 4 for the F sign (bass clef), and 3 for the C sign (alto clef). Line values can be used to specify positions outside the staff, such as a C clef positioned in the middle of a grand staff.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLClefOctaveChange(XMLElement):
    """
    The clef-octave-change element is used for transposing clefs. A treble clef for tenors would have a value of -1.
    """
    
    TYPE = XSDSimpleTypeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="clef-octave-change" type="xs:integer" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The clef-octave-change element is used for transposing clefs. A treble clef for tenors would have a value of -1.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLKeyStep(XMLElement):
    """
    Non-traditional key signatures are represented using a list of altered tones. The key-step element indicates the pitch step to be altered, represented using the same names as in the step element.
    """
    
    TYPE = XSDSimpleTypeStep
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="key-step" type="step">
    <xs:annotation>
        <xs:documentation>Non-traditional key signatures are represented using a list of altered tones. The key-step element indicates the pitch step to be altered, represented using the same names as in the step element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLKeyAlter(XMLElement):
    """
    Non-traditional key signatures are represented using a list of altered tones. The key-alter element represents the alteration for a given pitch step, represented with semitones in the same manner as the alter element.
    """
    
    TYPE = XSDSimpleTypeSemitones
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="key-alter" type="semitones">
    <xs:annotation>
        <xs:documentation>Non-traditional key signatures are represented using a list of altered tones. The key-alter element represents the alteration for a given pitch step, represented with semitones in the same manner as the alter element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLKeyAccidental(XMLElement):
    """
    The key-accidental type indicates the accidental to be displayed in a non-traditional key signature, represented in the same manner as the accidental type without the formatting attributes.
    """
    
    TYPE = XSDComplexTypeKeyAccidental
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="key-accidental" type="key-accidental" minOccurs="0">
    <xs:annotation>
        <xs:documentation>Non-traditional key signatures are represented using a list of altered tones. The key-accidental element indicates the accidental to be displayed in the key signature, represented in the same manner as the accidental element. It is used for disambiguating microtonal accidentals.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSlashType(XMLElement):
    """
    The slash-type element indicates the graphical note type to use for the display of repetition marks.
    """
    
    TYPE = XSDSimpleTypeNoteTypeValue
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="slash-type" type="note-type-value">
    <xs:annotation>
        <xs:documentation>The slash-type element indicates the graphical note type to use for the display of repetition marks.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLSlashDot(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="slash-dot" type="empty" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The slash-dot element is used to specify any augmentation dots in the note type used to display repetition marks.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLExceptVoice(XMLElement):
    """
    The except-voice element is used to specify a combination of slash notation and regular notation. Any note elements that are in voices specified by the except-voice elements are displayed in normal notation, in addition to the slash notation that is always displayed.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="except-voice" type="xs:string" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The except-voice element is used to specify a combination of slash notation and regular notation. Any note elements that are in voices specified by the except-voice elements are displayed in normal notation, in addition to the slash notation that is always displayed.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBeats(XMLElement):
    """
    The beats element indicates the number of beats, as found in the numerator of a time signature.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beats" type="xs:string">
    <xs:annotation>
        <xs:documentation>The beats element indicates the number of beats, as found in the numerator of a time signature.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBeatType(XMLElement):
    """
    The beat-type element indicates the beat unit, as found in the denominator of a time signature.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beat-type" type="xs:string">
    <xs:annotation>
        <xs:documentation>The beat-type element indicates the beat unit, as found in the denominator of a time signature.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLCancel(XMLElement):
    """
    A cancel element indicates that the old key signature should be cancelled before the new one appears. This will always happen when changing to C major or A minor and need not be specified then. The cancel value matches the fifths value of the cancelled key signature (e.g., a cancel of -2 will provide an explicit cancellation for changing from B flat major to F major). The optional location attribute indicates where the cancellation appears relative to the new key signature.
    """
    
    TYPE = XSDComplexTypeCancel
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="cancel" type="cancel" minOccurs="0" />
"""
                                     ))


class XMLFifths(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeFifths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="fifths" type="fifths" />
"""
                                     ))


class XMLMode(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeMode
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="mode" type="mode" minOccurs="0" />
"""
                                     ))


class XMLDiatonic(XMLElement):
    """
    The diatonic element specifies the number of pitch steps needed to go from written to sounding pitch. This allows for correct spelling of enharmonic transpositions. This value does not include octave-change values; the values for both elements need to be added to the written pitch to get the correct sounding pitch.
    """
    
    TYPE = XSDSimpleTypeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="diatonic" type="xs:integer" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The diatonic element specifies the number of pitch steps needed to go from written to sounding pitch. This allows for correct spelling of enharmonic transpositions. This value does not include octave-change values; the values for both elements need to be added to the written pitch to get the correct sounding pitch.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLChromatic(XMLElement):
    """
    The chromatic element represents the number of semitones needed to get from written to sounding pitch. This value does not include octave-change values; the values for both elements need to be added to the written pitch to get the correct sounding pitch.
    """
    
    TYPE = XSDSimpleTypeSemitones
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="chromatic" type="semitones">
    <xs:annotation>
        <xs:documentation>The chromatic element represents the number of semitones needed to get from written to sounding pitch. This value does not include octave-change values; the values for both elements need to be added to the written pitch to get the correct sounding pitch.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLOctaveChange(XMLElement):
    """
    The octave-change element indicates how many octaves to add to get from written pitch to sounding pitch. The octave-change element should be included when using transposition intervals of an octave or more, and should not be present for intervals of less than an octave.
    """
    
    TYPE = XSDSimpleTypeInteger
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="octave-change" type="xs:integer" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The octave-change element indicates how many octaves to add to get from written pitch to sounding pitch. The octave-change element should be included when using transposition intervals of an octave or more, and should not be present for intervals of less than an octave.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDouble(XMLElement):
    """
    The double type indicates that the music is doubled one octave from what is currently written. If the above attribute is set to yes, the doubling is one octave above what is written, as for mixed flute / piccolo parts in band literature. Otherwise the doubling is one octave below what is written, as for mixed cello / bass parts in orchestral literature.
    """
    
    TYPE = XSDComplexTypeDouble
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="double" type="double" minOccurs="0">
    <xs:annotation>
        <xs:documentation>If the double element is present, it indicates that the music is doubled one octave from what is currently written.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBeatUnit(XMLElement):
    """
    The beat-unit element indicates the graphical note type to use in a metronome mark.
    """
    
    TYPE = XSDSimpleTypeNoteTypeValue
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beat-unit" type="note-type-value">
    <xs:annotation>
        <xs:documentation>The beat-unit element indicates the graphical note type to use in a metronome mark.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLBeatUnitDot(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="beat-unit-dot" type="empty" minOccurs="0" maxOccurs="unbounded">
    <xs:annotation>
        <xs:documentation>The beat-unit-dot element is used to specify any augmentation dots for a metronome mark note.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLRoot(XMLElement):
    """
    The root type indicates a pitch like C, D, E vs. a scale degree like 1, 2, 3. It is used with chord symbols in popular music. The root element has a root-step and optional root-alter element similar to the step and alter elements, but renamed to distinguish the different musical meanings.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=root-step\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=root-alter\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeRoot
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="root" type="root" />
"""
                                     ))


class XMLNumeral(XMLElement):
    """
    The numeral type represents the Roman numeral or Nashville number part of a harmony. It requires that the key be specified in the encoding, either with a key or numeral-key element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=numeral-root\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=numeral-alter\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=numeral-key\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNumeral
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="numeral" type="numeral" />
"""
                                     ))


class XMLFunction(XMLElement):
    """
    The style-text type represents a text element with a print-style attribute group.
    """
    
    TYPE = XSDComplexTypeStyleText
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="function" type="style-text">
    <xs:annotation>
        <xs:documentation>The function element represents classical functional harmony with an indication like I, II, III rather than C, D, E. It represents the Roman numeral part of a functional harmony rather than the complete function itself. It has been deprecated as of MusicXML 4.0 in favor of the numeral element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLKind(XMLElement):
    """
    Kind indicates the type of chord. Degree elements can then add, subtract, or alter from these starting points
    
    The attributes are used to indicate the formatting of the symbol. Since the kind element is the constant in all the harmony-chord groups that can make up a polychord, many formatting attributes are here.
    
    The use-symbols attribute is yes if the kind should be represented when possible with harmony symbols rather than letters and numbers. These symbols include:
    
    	major: a triangle, like Unicode 25B3
    	minor: -, like Unicode 002D
    	augmented: +, like Unicode 002B
    	diminished: °, like Unicode 00B0
    	half-diminished: ø, like Unicode 00F8
    
    For the major-minor kind, only the minor symbol is used when use-symbols is yes. The major symbol is set using the symbol attribute in the degree-value element. The corresponding degree-alter value will usually be 0 in this case.
    
    The text attribute describes how the kind should be spelled in a score. If use-symbols is yes, the value of the text attribute follows the symbol. The stack-degrees attribute is yes if the degree elements should be stacked above each other. The parentheses-degrees attribute is yes if all the degrees should be in parentheses. The bracket-degrees attribute is yes if all the degrees should be in a bracket. If not specified, these values are implementation-specific. The alignment attributes are for the entire harmony-chord group of which this kind element is a part.
    
    The text attribute may use strings such as "13sus" that refer to both the kind and one or more degree elements. In this case, the corresponding degree elements should have the print-object attribute set to "no" to keep redundant alterations from being displayed.
    """
    
    TYPE = XSDComplexTypeKind
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="kind" type="kind" />
"""
                                     ))


class XMLInversion(XMLElement):
    """
    The inversion type represents harmony inversions. The value is a number indicating which inversion is used: 0 for root position, 1 for first inversion, etc.  The text attribute indicates how the inversion should be displayed in a score.
    """
    
    TYPE = XSDComplexTypeInversion
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="inversion" type="inversion" minOccurs="0" />
"""
                                     ))


class XMLBass(XMLElement):
    """
    The bass type is used to indicate a bass note in popular music chord symbols, e.g. G/C. It is generally not used in functional harmony, as inversion is generally not used in pop chord symbols. As with root, it is divided into step and alter elements, similar to pitches. The arrangement attribute specifies where the bass is displayed relative to what precedes it.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=bass-separator\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=bass-step\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=bass-alter\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeBass
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bass" type="bass" minOccurs="0" />
"""
                                     ))


class XMLDegree(XMLElement):
    """
    The degree type is used to add, alter, or subtract individual notes in the chord. The print-object attribute can be used to keep the degree from printing separately when it has already taken into account in the text attribute of the kind element. The degree-value and degree-type text attributes specify how the value and type of the degree should be displayed.
    
    A harmony of kind "other" can be spelled explicitly by using a series of degree elements together with a root.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=degree-value\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=degree-alter\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=degree-type\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeDegree
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="degree" type="degree" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLTopMargin(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="top-margin" type="tenths" />
"""
                                     ))


class XMLBottomMargin(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="bottom-margin" type="tenths" />
"""
                                     ))


class XMLPageLayout(XMLElement):
    """
    Page layout can be defined both in score-wide defaults and in the print element. Page margins are specified either for both even and odd pages, or via separate odd and even page number values. The type is not needed when used as part of a print element. If omitted when used in the defaults element, "both" is the default.
    
    If no page-layout element is present in the defaults element, default page layout values are chosen by the application.
    
    When used in the print element, the page-layout element affects the appearance of the current page only. All other pages use the default values as determined by the defaults element. If any child elements are missing from the page-layout element in a print element, the values determined by the defaults element are used there as well.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Sequence\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=page-height\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=page-width\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=page-margins\@minOccurs=0\@maxOccurs=2\n
    """
    
    TYPE = XSDComplexTypePageLayout
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="page-layout" type="page-layout" minOccurs="0" />
"""
                                     ))


class XMLSystemLayout(XMLElement):
    """
    A system is a group of staves that are read and played simultaneously. System layout includes left and right margins and the vertical distance from the previous system. The system distance is measured from the bottom line of the previous system to the top line of the current system. It is ignored for the first system on a page. The top system distance is measured from the page's top margin to the top line of the first system. It is ignored for all but the first system on a page.
    
    Sometimes the sum of measure widths in a system may not equal the system width specified by the layout elements due to roundoff or other errors. The behavior when reading MusicXML files in these cases is application-dependent. For instance, applications may find that the system layout data is more reliable than the sum of the measure widths, and adjust the measure widths accordingly.
    
    When used in the defaults element, the system-layout element defines a default appearance for all systems in the score. If no system-layout element is present in the defaults element, default system layout values are chosen by the application.
    
    When used in the print element, the system-layout element affects the appearance of the current system only. All other systems use the default values as determined by the defaults element. If any child elements are missing from the system-layout element in a print element, the values determined by the defaults element are used there as well. This type of system-layout element need only be read from or written to the first visible part in the score.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=system-margins\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=system-distance\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=top-system-distance\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=system-dividers\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeSystemLayout
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="system-layout" type="system-layout" minOccurs="0" />
"""
                                     ))


class XMLStaffLayout(XMLElement):
    """
    Staff layout includes the vertical distance from the bottom line of the previous staff in this system to the top line of the staff specified by the number attribute. The optional number attribute refers to staff numbers within the part, from top to bottom on the system. A value of 1 is used if not present.
    
    When used in the defaults element, the values apply to all systems in all parts. When used in the print element, the values apply to the current system only. This value is ignored for the first staff in a system.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=staff-distance\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeStaffLayout
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="staff-layout" type="staff-layout" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLLeftMargin(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="left-margin" type="tenths" />
"""
                                     ))


class XMLRightMargin(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeTenths
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="right-margin" type="tenths" />
"""
                                     ))


class XMLDuration(XMLElement):
    """
    Duration is a positive number specified in division units. This is the intended duration vs. notated duration (for instance, differences in dotted notes in Baroque-era music). Differences in duration specific to an interpretation or performance should be represented using the note element's attack and release attributes.

The duration element moves the musical position when used in backup elements, forward elements, and note elements that do not contain a chord child element.
    """
    
    TYPE = XSDSimpleTypePositiveDivisions
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="duration" type="positive-divisions">
    <xs:annotation>
        <xs:documentation>Duration is a positive number specified in division units. This is the intended duration vs. notated duration (for instance, differences in dotted notes in Baroque-era music). Differences in duration specific to an interpretation or performance should be represented using the note element's attack and release attributes.

The duration element moves the musical position when used in backup elements, forward elements, and note elements that do not contain a chord child element.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDisplayStep(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeStep
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="display-step" type="step" />
"""
                                     ))


class XMLDisplayOctave(XMLElement):
    """
    
    """
    
    TYPE = XSDSimpleTypeOctave
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="display-octave" type="octave" />
"""
                                     ))


class XMLChord(XMLElement):
    """
    The empty type represents an empty element with no attributes.
    """
    
    TYPE = XSDComplexTypeEmpty
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="chord" type="empty" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The chord element indicates that this note is an additional chord tone with the preceding note.

The duration of a chord note does not move the musical position within a measure. That is done by the duration of the first preceding note without a chord element. Thus the duration of a chord note cannot be longer than the preceding note.
							
In most cases the duration will be the same as the preceding note. However it can be shorter in situations such as multiple stops for string instruments.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLPitch(XMLElement):
    """
    Pitch is represented as a combination of the step of the diatonic scale, the chromatic alteration, and the octave.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=step\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=alter\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=octave\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePitch
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="pitch" type="pitch" />
"""
                                     ))


class XMLUnpitched(XMLElement):
    """
    The unpitched type represents musical elements that are notated on the staff but lack definite pitch, such as unpitched percussion and speaking voice. If the child elements are not present, the note is placed on the middle line of the staff. This is generally used with a one-line staff. Notes in percussion clef should always use an unpitched element rather than a pitch element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=display-step-octave\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=display-step\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=display-octave\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeUnpitched
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="unpitched" type="unpitched" />
"""
                                     ))


class XMLRest(XMLElement):
    """
    The rest element indicates notated rests or silences. Rest elements are usually empty, but placement on the staff can be specified using display-step and display-octave elements. If the measure attribute is set to yes, this indicates this is a complete measure rest.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=display-step-octave\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=display-step\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=display-octave\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeRest
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="rest" type="rest" />
"""
                                     ))


class XMLNote(XMLElement):
    """
    Notes are the most common type of MusicXML data. The MusicXML format distinguishes between elements used for sound information and elements used for notation information (e.g., tie is used for sound, tied for notation). Thus grace notes do not have a duration element. Cue notes have a duration element, as do forward elements, but no tie elements. Having these two types of information available can make interchange easier, as some programs handle one type of information more readily than the other.
    
    The print-leger attribute is used to indicate whether leger lines are printed. Notes without leger lines are used to indicate indeterminate high and low notes. By default, it is set to yes. If print-object is set to no, print-leger is interpreted to also be set to no if not present. This attribute is ignored for rests.
    
    The dynamics and end-dynamics attributes correspond to MIDI 1.0's Note On and Note Off velocities, respectively. They are expressed in terms of percentages of the default forte value (90 for MIDI 1.0).
    
    The attack and release attributes are used to alter the starting and stopping time of the note from when it would otherwise occur based on the flow of durations - information that is specific to a performance. They are expressed in terms of divisions, either positive or negative. A note that starts a tie should not have a release attribute, and a note that stops a tie should not have an attack attribute. The attack and release attributes are independent of each other. The attack attribute only changes the starting time of a note, and the release attribute only changes the stopping time of a note.
    
    If a note is played only particular times through a repeat, the time-only attribute shows which times to play the note.
    
    The pizzicato attribute is used when just this note is sounded pizzicato, vs. the pizzicato element which changes overall playback between pizzicato and arco.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=full-note\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=chord\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=pitch\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=unpitched\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=rest\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=tie\@minOccurs=0\@maxOccurs=2\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=cue\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=full-note\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=chord\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=pitch\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=unpitched\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=rest\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=grace\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Group\@name=full-note\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=chord\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=pitch\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=unpitched\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=rest\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=tie\@minOccurs=0\@maxOccurs=2\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=cue\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Group\@name=full-note\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=chord\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=pitch\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=unpitched\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- \- Element\@name=rest\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=instrument\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Group\@name=editorial-voice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=voice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=voice\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=type\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=dot\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=accidental\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=time-modification\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=stem\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=notehead\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=notehead-text\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=staff\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=staff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=beam\@minOccurs=0\@maxOccurs=8\n
    \- \- Element\@name=notations\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=lyric\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=play\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=listen\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeNote
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="note" type="note" />
"""
                                     ))


class XMLBackup(XMLElement):
    """
    The backup and forward elements are required to coordinate multiple voices in one part, including music on multiple staves. The backup type is generally used to move between voices and staves. Thus the backup element does not include voice or staff elements. Duration values should always be positive, and should not cross measure boundaries or mid-measure changes in the divisions value.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeBackup
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="backup" type="backup" />
"""
                                     ))


class XMLForward(XMLElement):
    """
    The backup and forward elements are required to coordinate multiple voices in one part, including music on multiple staves. The forward element is generally used within voices and staves. Duration values should always be positive, and should not cross measure boundaries or mid-measure changes in the divisions value.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=editorial-voice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=voice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=voice\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=staff\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=staff\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeForward
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="forward" type="forward" />
"""
                                     ))


class XMLDirection(XMLElement):
    """
    A direction is a musical indication that is not necessarily attached to a specific note. Two or more may be combined to indicate words followed by the start of a dashed line, the end of a wedge followed by dynamics, etc. For applications where a specific direction is indeed attached to a specific note, the direction element can be associated with the first note element that follows it in score order that is not in a different voice.
    
    By default, a series of direction-type elements and a series of child elements of a direction-type within a single direction element follow one another in sequence visually. For a series of direction-type children, non-positional formatting attributes are carried over from the previous element by default.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=direction-type\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Element\@name=offset\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=editorial-voice-direction\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=voice\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=voice\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=staff\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=staff\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=sound\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=listening\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeDirection
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="direction" type="direction" />
"""
                                     ))


class XMLAttributes(XMLElement):
    """
    The attributes element contains musical information that typically changes on measure boundaries. This includes key and time signatures, clefs, transpositions, and staving. When attributes are changed mid-measure, it affects the music in score order, not in MusicXML document order.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=divisions\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=key\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=time\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=staves\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=part-symbol\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=instruments\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=clef\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=staff-details\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=transpose\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=for-part\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=directive\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=measure-style\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeAttributes
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="attributes" type="attributes" />
"""
                                     ))


class XMLHarmony(XMLElement):
    """
    The harmony type represents harmony analysis, including chord symbols in popular music as well as functional harmony analysis in classical music.
    
    If there are alternate harmonies possible, this can be specified using multiple harmony elements differentiated by type. Explicit harmonies have all note present in the music; implied have some notes missing but implied; alternate represents alternate analyses.
    
    The print-object attribute controls whether or not anything is printed due to the harmony element. The print-frame attribute controls printing of a frame or fretboard diagram. The print-style attribute group sets the default for the harmony, but individual elements can override this with their own print-style values. The arrangement attribute specifies how multiple harmony-chord groups are arranged relative to each other. Harmony-chords with vertical arrangement are separated by horizontal lines. Harmony-chords with diagonal or horizontal arrangement are separated by diagonal lines or slashes.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=harmony-chord\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=root\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=numeral\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=function\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=kind\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=inversion\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=bass\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=degree\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=frame\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=offset\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=staff\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=staff\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeHarmony
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="harmony" type="harmony" />
"""
                                     ))


class XMLFiguredBass(XMLElement):
    """
    The figured-bass element represents figured bass notation. Figured bass elements take their position from the first regular note (not a grace note or chord note) that follows in score order. The optional duration element is used to indicate changes of figures under a note.
    
    Figures are ordered from top to bottom. The value of parentheses is "no" if not present.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=figure\@minOccurs=1\@maxOccurs=unbounded\n
    \- \- Group\@name=duration\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=duration\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeFiguredBass
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="figured-bass" type="figured-bass" />
"""
                                     ))


class XMLPrint(XMLElement):
    """
    The print type contains general printing parameters, including layout elements. The part-name-display and part-abbreviation-display elements may also be used here to change how a part name or abbreviation is displayed over the course of a piece. They take effect when the current measure or a succeeding measure starts a new system.
    
    Layout group elements in a print element only apply to the current page, system, or staff. Music that follows continues to take the default values from the layout determined by the defaults element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=layout\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=page-layout\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=system-layout\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=staff-layout\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=measure-layout\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=measure-numbering\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=part-name-display\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=part-abbreviation-display\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePrint
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="print" type="print" />
"""
                                     ))


class XMLBarline(XMLElement):
    """
    If a barline is other than a normal single barline, it should be represented by a barline type that describes it. This includes information about repeats and multiple endings, as well as line style. Barline data is on the same level as the other musical data in a score - a child of a measure in a partwise score, or a part in a timewise score. This allows for barlines within measures, as in dotted barlines that subdivide measures in complex meters. The two fermata elements allow for fermatas on both sides of the barline (the lower one inverted).
    
    Barlines have a location attribute to make it easier to process barlines independently of the other musical data in a score. It is often easier to set up measures separately from entering notes. The location attribute must match where the barline element occurs within the rest of the musical data in the score. If location is left, it should be the first element in the measure, aside from the print, bookmark, and link elements. If location is right, it should be the last element, again with the possible exception of the print, bookmark, and link elements. If no location is specified, the right barline is the default. The segno, coda, and divisions attributes work the same way as in the sound element. They are used for playback when barline elements contain segno or coda child elements.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=bar-style\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=wavy-line\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=segno\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=coda\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=fermata\@minOccurs=0\@maxOccurs=2\n
    \- \- Element\@name=ending\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=repeat\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeBarline
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="barline" type="barline" />
"""
                                     ))


class XMLGrouping(XMLElement):
    """
    The grouping type is used for musical analysis. When the type attribute is "start" or "single", it usually contains one or more feature elements. The number attribute is used for distinguishing between overlapping and hierarchical groupings. The member-of attribute allows for easy distinguishing of what grouping elements are in what hierarchy. Feature elements contained within a "stop" type of grouping may be ignored.
    
    This element is flexible to allow for different types of analyses. Future versions of the MusicXML format may add elements that can represent more standardized categories of analysis data, allowing for easier data sharing.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=feature\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeGrouping
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="grouping" type="grouping" />
"""
                                     ))


class XMLPartGroup(XMLElement):
    """
    The part-group element indicates groupings of parts in the score, usually indicated by braces and brackets. Braces that are used for multi-staff parts should be defined in the attributes element for that part. The part-group start element appears before the first score-part in the group. The part-group stop element appears after the last score-part in the group.
    
    The number attribute is used to distinguish overlapping and nested part-groups, not the sequence of groups. As with parts, groups can have a name and abbreviation. Values for the child elements are ignored at the stop of a group.
    
    A part-group element is not needed for a single multi-staff part. By default, multi-staff parts include a brace symbol and (if appropriate given the bar-style) common barlines. The symbol formatting for a multi-staff part can be more fully specified using the part-symbol element.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=group-name\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=group-name-display\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=group-abbreviation\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=group-abbreviation-display\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=group-symbol\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=group-barline\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=group-time\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=editorial\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=footnote\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=footnote\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Group\@name=level\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=level\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePartGroup
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-group" type="part-group" />
"""
                                     ))


class XMLWork(XMLElement):
    """
    Works are optionally identified by number and title. The work type also may indicate a link to the opus document that composes multiple scores into a collection.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=work-number\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=work-title\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=opus\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeWork
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="work" type="work" minOccurs="0" />
"""
                                     ))


class XMLMovementNumber(XMLElement):
    """
    The movement-number element specifies the number of a movement.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="movement-number" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The movement-number element specifies the number of a movement.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLMovementTitle(XMLElement):
    """
    The movement-title element specifies the title of a movement, not including its number.
    """
    
    TYPE = XSDSimpleTypeString
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="movement-title" type="xs:string" minOccurs="0">
    <xs:annotation>
        <xs:documentation>The movement-title element specifies the title of a movement, not including its number.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))


class XMLDefaults(XMLElement):
    """
    The defaults type specifies score-wide defaults for scaling; whether or not the file is a concert score; layout; and default values for the music font, word font, lyric font, and lyric language. Except for the concert-score element, if any defaults are missing, the choice of what to use is determined by the application.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=scaling\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=concert-score\@minOccurs=0\@maxOccurs=1\n
    \- \- Group\@name=layout\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=page-layout\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=system-layout\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=staff-layout\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=appearance\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=music-font\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=word-font\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=lyric-font\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=lyric-language\@minOccurs=0\@maxOccurs=unbounded\n
    """
    
    TYPE = XSDComplexTypeDefaults
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="defaults" type="defaults" minOccurs="0" />
"""
                                     ))


class XMLCredit(XMLElement):
    """
    The credit type represents the appearance of the title, composer, arranger, lyricist, copyright, dedication, and other text, symbols, and graphics that commonly appear on the first page of a score. The credit-words, credit-symbol, and credit-image elements are similar to the words, symbol, and image elements for directions. However, since the credit is not part of a measure, the default-x and default-y attributes adjust the origin relative to the bottom left-hand corner of the page. The enclosure for credit-words and credit-symbol is none by default.
    
    By default, a series of credit-words and credit-symbol elements within a single credit element follow one another in sequence visually. Non-positional formatting attributes are carried over from the previous element by default.
    
    The page attribute for the credit element specifies the page number where the credit should appear. This is an integer value that starts with 1 for the first page. Its value is 1 by default. Since credits occur before the music, these page numbers do not refer to the page numbering specified by the print element's page-number attribute.
    
    The credit-type element indicates the purpose behind a credit. Multiple types of data may be combined in a single credit, so multiple elements may be used. Standard values include page number, title, subtitle, composer, arranger, lyricist, rights, and part name.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=credit-type\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=link\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=bookmark\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Element\@name=credit-image\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=credit-words\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=credit-symbol\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- \- \- \- \- Element\@name=link\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- \- \- \- \- Element\@name=bookmark\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- \- \- \- \- Choice\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=credit-words\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- \- \- Element\@name=credit-symbol\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeCredit
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="credit" type="credit" minOccurs="0" maxOccurs="unbounded" />
"""
                                     ))


class XMLPartList(XMLElement):
    """
    The part-list identifies the different musical parts in this document. Each part has an ID that is used later within the musical data. Since parts may be encoded separately and combined later, identification elements are present at both the score and score-part levels. There must be at least one score-part, combined as desired with part-group elements that indicate braces and brackets. Parts are ordered from top to bottom in a score based on the order in which they appear in the part-list.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=part-group\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=part-group\@minOccurs=1\@maxOccurs=1\n
    \- \- Group\@name=score-part\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Element\@name=score-part\@minOccurs=1\@maxOccurs=1\n
    \- \- Choice\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Group\@name=part-group\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=part-group\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- Group\@name=score-part\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- \- \- \- \- \- \- Element\@name=score-part\@minOccurs=1\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypePartList
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="part-list" type="part-list" />
"""
                                     ))


class XMLScorePart(XMLElement):
    """
    The score-part type collects part-wide information for each part in a score. Often, each MusicXML part corresponds to a track in a Standard MIDI Format 1 file. In this case, the midi-device element is used to make a MIDI device or port assignment for the given track or specific MIDI instruments. Initial midi-instrument assignments may be made here as well. The score-instrument elements are used when there are multiple instruments per track.\n
    XSD structure:\n
    Sequence\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=identification\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=part-link\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=part-name\@minOccurs=1\@maxOccurs=1\n
    \- \- Element\@name=part-name-display\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=part-abbreviation\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=part-abbreviation-display\@minOccurs=0\@maxOccurs=1\n
    \- \- Element\@name=group\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=score-instrument\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Element\@name=player\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- Sequence\@minOccurs=0\@maxOccurs=unbounded\n
    \- \- \- \- Element\@name=midi-device\@minOccurs=0\@maxOccurs=1\n
    \- \- \- \- Element\@name=midi-instrument\@minOccurs=0\@maxOccurs=1\n
    """
    
    TYPE = XSDComplexTypeScorePart
    XSD_TREE = XSDTree(ET.fromstring("""
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema" name="score-part" type="score-part">
    <xs:annotation>
        <xs:documentation>Each MusicXML part corresponds to a track in a Standard MIDI Format 1 file. The score-instrument elements are used when there are multiple instruments per track. The midi-device element is used to make a MIDI device or port assignment for the given track. Initial midi-instrument assignments may be made here as well.</xs:documentation>
    </xs:annotation>
</xs:element>
"""
                                     ))

__all__=['XMLScorePartwise', 'XMLPart', 'XMLMeasure', 'XMLDirective', 'XMLP', 'XMLPp', 'XMLPpp', 'XMLPppp', 'XMLPpppp', 'XMLPppppp', 'XMLF', 'XMLFf', 'XMLFff', 'XMLFfff', 'XMLFffff', 'XMLFfffff', 'XMLMp', 'XMLMf', 'XMLSf', 'XMLSfp', 'XMLSfpp', 'XMLFp', 'XMLRf', 'XMLRfz', 'XMLSfz', 'XMLSffz', 'XMLFz', 'XMLN', 'XMLPf', 'XMLSfzp', 'XMLOtherDynamics', 'XMLMidiChannel', 'XMLMidiName', 'XMLMidiBank', 'XMLMidiProgram', 'XMLMidiUnpitched', 'XMLVolume', 'XMLPan', 'XMLElevation', 'XMLDisplayText', 'XMLAccidentalText', 'XMLIpa', 'XMLMute', 'XMLSemiPitched', 'XMLOtherPlay', 'XMLDivisions', 'XMLKey', 'XMLTime', 'XMLStaves', 'XMLPartSymbol', 'XMLInstruments', 'XMLClef', 'XMLStaffDetails', 'XMLTranspose', 'XMLForPart', 'XMLMeasureStyle', 'XMLPartClef', 'XMLPartTranspose', 'XMLTimeRelation', 'XMLKeyOctave', 'XMLMultipleRest', 'XMLMeasureRepeat', 'XMLBeatRepeat', 'XMLSlash', 'XMLStaffType', 'XMLStaffLines', 'XMLLineDetail', 'XMLStaffTuning', 'XMLCapo', 'XMLStaffSize', 'XMLInterchangeable', 'XMLSenzaMisura', 'XMLBarStyle', 'XMLWavyLine', 'XMLSegno', 'XMLCoda', 'XMLFermata', 'XMLEnding', 'XMLRepeat', 'XMLAccordionHigh', 'XMLAccordionMiddle', 'XMLAccordionLow', 'XMLBassSeparator', 'XMLBassStep', 'XMLBassAlter', 'XMLDegreeValue', 'XMLDegreeAlter', 'XMLDegreeType', 'XMLDirectionType', 'XMLOffset', 'XMLSound', 'XMLListening', 'XMLRehearsal', 'XMLWords', 'XMLSymbol', 'XMLWedge', 'XMLDynamics', 'XMLDashes', 'XMLBracket', 'XMLPedal', 'XMLMetronome', 'XMLOctaveShift', 'XMLHarpPedals', 'XMLDamp', 'XMLDampAll', 'XMLEyeglasses', 'XMLStringMute', 'XMLScordatura', 'XMLImage', 'XMLPrincipalVoice', 'XMLPercussion', 'XMLAccordionRegistration', 'XMLStaffDivide', 'XMLOtherDirection', 'XMLFrameStrings', 'XMLFrameFrets', 'XMLFirstFret', 'XMLFrameNote', 'XMLString', 'XMLFret', 'XMLFingering', 'XMLBarre', 'XMLFeature', 'XMLFrame', 'XMLPedalTuning', 'XMLSync', 'XMLOtherListening', 'XMLBeatUnitTied', 'XMLPerMinute', 'XMLMetronomeArrows', 'XMLMetronomeNote', 'XMLMetronomeRelation', 'XMLMetronomeType', 'XMLMetronomeDot', 'XMLMetronomeBeam', 'XMLMetronomeTied', 'XMLMetronomeTuplet', 'XMLNumeralRoot', 'XMLNumeralAlter', 'XMLNumeralKey', 'XMLNumeralFifths', 'XMLNumeralMode', 'XMLPedalStep', 'XMLPedalAlter', 'XMLGlass', 'XMLMetal', 'XMLWood', 'XMLPitched', 'XMLMembrane', 'XMLEffect', 'XMLTimpani', 'XMLBeater', 'XMLStick', 'XMLStickLocation', 'XMLOtherPercussion', 'XMLMeasureLayout', 'XMLMeasureNumbering', 'XMLPartNameDisplay', 'XMLPartAbbreviationDisplay', 'XMLRootStep', 'XMLRootAlter', 'XMLAccord', 'XMLInstrumentChange', 'XMLMidiDevice', 'XMLMidiInstrument', 'XMLPlay', 'XMLSwing', 'XMLStickType', 'XMLStickMaterial', 'XMLStraight', 'XMLFirst', 'XMLSecond', 'XMLSwingType', 'XMLSwingStyle', 'XMLEncodingDate', 'XMLEncoder', 'XMLSoftware', 'XMLEncodingDescription', 'XMLSupports', 'XMLCreator', 'XMLRights', 'XMLEncoding', 'XMLSource', 'XMLRelation', 'XMLMiscellaneous', 'XMLMiscellaneousField', 'XMLLineWidth', 'XMLNoteSize', 'XMLDistance', 'XMLGlyph', 'XMLOtherAppearance', 'XMLMeasureDistance', 'XMLPageHeight', 'XMLPageWidth', 'XMLPageMargins', 'XMLMillimeters', 'XMLTenths', 'XMLStaffDistance', 'XMLLeftDivider', 'XMLRightDivider', 'XMLSystemMargins', 'XMLSystemDistance', 'XMLTopSystemDistance', 'XMLSystemDividers', 'XMLAccent', 'XMLStrongAccent', 'XMLStaccato', 'XMLTenuto', 'XMLDetachedLegato', 'XMLStaccatissimo', 'XMLSpiccato', 'XMLScoop', 'XMLPlop', 'XMLDoit', 'XMLFalloff', 'XMLBreathMark', 'XMLCaesura', 'XMLStress', 'XMLUnstress', 'XMLSoftAccent', 'XMLOtherArticulation', 'XMLArrowDirection', 'XMLArrowStyle', 'XMLArrowhead', 'XMLCircularArrow', 'XMLBendAlter', 'XMLPreBend', 'XMLRelease', 'XMLWithBar', 'XMLPrefix', 'XMLFigureNumber', 'XMLSuffix', 'XMLExtend', 'XMLFigure', 'XMLHarmonClosed', 'XMLNatural', 'XMLArtificial', 'XMLBasePitch', 'XMLTouchingPitch', 'XMLSoundingPitch', 'XMLHoleType', 'XMLHoleClosed', 'XMLHoleShape', 'XMLAssess', 'XMLWait', 'XMLOtherListen', 'XMLSyllabic', 'XMLText', 'XMLElision', 'XMLLaughing', 'XMLHumming', 'XMLEndLine', 'XMLEndParagraph', 'XMLTied', 'XMLSlur', 'XMLTuplet', 'XMLGlissando', 'XMLSlide', 'XMLOrnaments', 'XMLTechnical', 'XMLArticulations', 'XMLArpeggiate', 'XMLNonArpeggiate', 'XMLAccidentalMark', 'XMLOtherNotation', 'XMLGrace', 'XMLTie', 'XMLCue', 'XMLInstrument', 'XMLType', 'XMLDot', 'XMLAccidental', 'XMLTimeModification', 'XMLStem', 'XMLNotehead', 'XMLNoteheadText', 'XMLBeam', 'XMLNotations', 'XMLLyric', 'XMLListen', 'XMLTrillMark', 'XMLTurn', 'XMLDelayedTurn', 'XMLInvertedTurn', 'XMLDelayedInvertedTurn', 'XMLVerticalTurn', 'XMLInvertedVerticalTurn', 'XMLShake', 'XMLMordent', 'XMLInvertedMordent', 'XMLSchleifer', 'XMLTremolo', 'XMLHaydn', 'XMLOtherOrnament', 'XMLStep', 'XMLAlter', 'XMLOctave', 'XMLUpBow', 'XMLDownBow', 'XMLHarmonic', 'XMLOpenString', 'XMLThumbPosition', 'XMLPluck', 'XMLDoubleTongue', 'XMLTripleTongue', 'XMLStopped', 'XMLSnapPizzicato', 'XMLHammerOn', 'XMLPullOff', 'XMLBend', 'XMLTap', 'XMLHeel', 'XMLToe', 'XMLFingernails', 'XMLHole', 'XMLArrow', 'XMLHandbell', 'XMLBrassBend', 'XMLFlip', 'XMLSmear', 'XMLOpen', 'XMLHalfMuted', 'XMLHarmonMute', 'XMLGolpe', 'XMLOtherTechnical', 'XMLActualNotes', 'XMLNormalNotes', 'XMLNormalType', 'XMLNormalDot', 'XMLTupletActual', 'XMLTupletNormal', 'XMLTupletNumber', 'XMLTupletType', 'XMLTupletDot', 'XMLCreditType', 'XMLLink', 'XMLBookmark', 'XMLCreditImage', 'XMLCreditWords', 'XMLCreditSymbol', 'XMLScaling', 'XMLConcertScore', 'XMLAppearance', 'XMLMusicFont', 'XMLWordFont', 'XMLLyricFont', 'XMLLyricLanguage', 'XMLGroupName', 'XMLGroupNameDisplay', 'XMLGroupAbbreviation', 'XMLGroupAbbreviationDisplay', 'XMLGroupSymbol', 'XMLGroupBarline', 'XMLGroupTime', 'XMLInstrumentLink', 'XMLGroupLink', 'XMLPlayerName', 'XMLInstrumentName', 'XMLInstrumentAbbreviation', 'XMLIdentification', 'XMLPartLink', 'XMLPartName', 'XMLPartAbbreviation', 'XMLGroup', 'XMLScoreInstrument', 'XMLPlayer', 'XMLVirtualLibrary', 'XMLVirtualName', 'XMLWorkNumber', 'XMLWorkTitle', 'XMLOpus', 'XMLFootnote', 'XMLLevel', 'XMLStaff', 'XMLTuningStep', 'XMLTuningAlter', 'XMLTuningOctave', 'XMLInstrumentSound', 'XMLSolo', 'XMLEnsemble', 'XMLVirtualInstrument', 'XMLVoice', 'XMLSign', 'XMLLine', 'XMLClefOctaveChange', 'XMLKeyStep', 'XMLKeyAlter', 'XMLKeyAccidental', 'XMLSlashType', 'XMLSlashDot', 'XMLExceptVoice', 'XMLBeats', 'XMLBeatType', 'XMLCancel', 'XMLFifths', 'XMLMode', 'XMLDiatonic', 'XMLChromatic', 'XMLOctaveChange', 'XMLDouble', 'XMLBeatUnit', 'XMLBeatUnitDot', 'XMLRoot', 'XMLNumeral', 'XMLFunction', 'XMLKind', 'XMLInversion', 'XMLBass', 'XMLDegree', 'XMLTopMargin', 'XMLBottomMargin', 'XMLPageLayout', 'XMLSystemLayout', 'XMLStaffLayout', 'XMLLeftMargin', 'XMLRightMargin', 'XMLDuration', 'XMLDisplayStep', 'XMLDisplayOctave', 'XMLChord', 'XMLPitch', 'XMLUnpitched', 'XMLRest', 'XMLNote', 'XMLBackup', 'XMLForward', 'XMLDirection', 'XMLAttributes', 'XMLHarmony', 'XMLFiguredBass', 'XMLPrint', 'XMLBarline', 'XMLGrouping', 'XMLPartGroup', 'XMLWork', 'XMLMovementNumber', 'XMLMovementTitle', 'XMLDefaults', 'XMLCredit', 'XMLPartList', 'XMLScorePart']
