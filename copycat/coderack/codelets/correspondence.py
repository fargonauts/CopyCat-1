# Copyright (c) 2007-2009 Joseph Hager.
#
# Copycat is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License,
# as published by the Free Software Foundation.
# 
# Copycat is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Copycat; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

import copycat.toolbox as toolbox
from copycat.coderack import Codelet
import copycat.slipnet as nodes

class CorrespondenceBottomUpScout(Codelet):
    '''
    Chooses two objects, one from the initial string and one from the
    target string, probabilistically by inter string salience. Finds all
    concept mappings between nodes at most one link away. If any concept
    mappings can be made between distinguishing descriptors, propoes a
    correspondence between the two objects, including all the concept
    mappings. Posts a correspondence strength tester codelet with urgency
    a funcion of the average strength of the distinguishing concept
    mappings.
    '''
    def run(self, coderack, slipnet, workspace):
        # Choose two objects.
        object1 = workspace.initial_string.choose_object('inter_string_salience')
        object2 = workspace.target_string.choose_object('inter_string_salience')

        # If one object spans the whole string and the other does not, fizzle.
        if object1.spans_whole_string() != object2.spans_whole_string():
            return

        # Get the possible concept mappings.
        mappings = workspace.get_concept_mappings(object1, object2,
                                                  object1.relevant_descriptions(),
                                                  object2.relevant_descriptions())
        if not mappings:
            return

        # Decide whether or not to continue based on slippability.
        possible = False
        for mapping in mappings:
            probability = mapping.slippability() / 100.0
            probability = workspace.temperature_adjusted_probability(probability)
            if toolbox.flip_coin(probability):
                possible = True
        if not possible:
            return

        # Check if there are any distinguishing mappings.
        distinguished_mappings = [m for m in mappings if m.is_distinguishing()]
        if not distinguished_mappings:
            return

        # If both objects span the strings, check if description needs flipped.
        possible_opposite_mappings = []
        for mapping in distinguished_mappings:
            description_type = mapping.description_type1
            if description_type != 'plato_string_position_category' and \
               description_type != 'plato_bond_facet':
                   possible_opposite_mappings.append(mapping)

        opposite_descriptions = [m.description_type1 for m in mappings]
        if all([object1.is_string_spanning_group(),
                object2.is_string_spanning_group(),
                not nodes.plato_opposite.is_active(),
                nodes.are_all_opposite_concept_mappings(possible_opposite_mappings),
                nodes.plato_direction_category in opposite_descriptions]):
            old_object2_string_number = object2.string_number
            object2 = object2.flipped_version()
            object2.string_number = old_object2_string_number
            mappings = self.concept_mappings(object1, object2,
                                             object1.relevant_descriptions(),
                                             object2.relevant_descriptions())

        return workspace.propose_correspondence(object1, object2, mappings, True)

class CorrespondenceBuilder(Codelet):
    '''
    Attempts to build the proposed correspondence, fighting it out with
    competitors if necessary.
    '''
    def run(self, coderack, slipnet, workspace):
        correspondence = self.arguments[0]
        flip_obj2 = self.arguments[1]

        object1 = correspondence.object1
        object2 = correspondence.object2

        flipped = object2.flipped_version()
        existing_object2_group = workspace.target_string.is_group_present(flipped)

        # If the objects do not exist anymore, then fizzle.
        objects = self.objects()
        if (object1 not in objects) or \
            ((object2 not in objects) and \
            (not (flip_object2 and existing_object2_group))):
            return

        # If the correspondence exists, add and activiate concept mappings.
        existing_correspondence = self.correspondence_present(correspondence)
        if existing_correspondence:
            self.delete_proposed_correspondence(correspondence)
            labels = [m.label for m in correspondence.concept_mappings]
            for label in labels:
                label.buffer += self.activation
            mappings_to_add = []
            for mapping in correspondence.concept_mappings:
                if not correspondence.mapping_present(mapping):
                    mappings_to_add.append(mapping)
            existing_correspondence.add_concept_mappings(mappings_to_add)
            return

        # If any concept mappings are no longer relevant, then fizzle.
        for mapping in correspondence.concept_mappings:
            if not mapping.relevant:
                return

        # Remove the proposed correpondence from proposed correspondences.
        self.delete_proposed_correspondence(correspondence)

        # The proposed correspondence must win against all incompatible ones.
        incompatible_correspondences = correspondence.incompatible_corresondences()
        for incompatible_correspondence in incompatible_correspondences:
            if not self.fight_it_out(correspondence,
                                     correspondence.letter_span,
                                     [incompatible_correspondence],
                                     incompatible_correspondence.letter_span):
                return

        # The proposed correspondence must win against any incompatible bond.
        if (object1.leftmost_in_string or object1.rightmost_in_string) and \
               (object2.leftmost_in_string or object2.rightmost_in_string):
            incompatible_bond = correspondence.incompatible_bond()
            if incompatible_bond:
                if not self.fight_it_out(correspondence, 3,
                                         [incompatible_bond], 2):
                    return
                # If the bond is in a group, fight against it as well.
                incompatible_group = incompatible_bond.group
                if incompatible_group:
                    if not self.fight_it_out(correspondence, 1,
                                             [incompatible_group], 1):
                        return

        # If the desired object2 is flipped its existing group.
        if flip_object2:
            if not self.fight_it_out(correspondence, 1,
                                     [existing_object2_group], 1):
                return

        # The proposed corresondence must win against an incompatible rule.
        incompatible_rule = correspondence.incompatible_rule()
        if incompatible_rule:
            if not self.fight_it_out(correspondence, 1, [self.rule], 1):
                return

        # Break all incompatible structures.
        if incompatible_correspondences:
            for incompatible_correspondence in incompatible_correspondences:
                self.break_correspondence(incompatible_correspondence)

        if incompatible_bond:
            self.break_bond(incompatible_bond)

        if incompatible_group:
            self.break_group(incompatible_group)

        if existing_object2_group:
            self.break_group(existing_object2_group)
            for bond in existing_object2_group.bonds():
                self.break_bond(bond)
            for bond in object2.bonds():
                self.build_bond(bond)
            self.build_group(object2)

        if incompatible_rule:
            self.break_rule(self.rule)

        # Build the correspondence.
        self.build_correspondence(correspondence)

class CorrespondenceImportantObjectScout(Codelet):
    '''
    Chooses an object from the initial string probabilistically based on
    importance. Picks a description of the object probabilistically and
    looks for an object in the target string with the same description,
    modulo the appropriate slippage, if any of the slippages currently in
    the workspace apply. Then finds all concept mappings between nodes at
    most one link away. Makes a proposed correspondence between the two
    objects, including all the concept mappings. Posts a correspondence
    strength tester codelet with urgency a function of the average
    strength of the distinguishing concept mappings.
    '''
    def run(self, coderack, slipnet, workspace):
        # Choose an object.
        object1 = workspace.initial_string.choose_object('relative_importance')

        # Choose a description by conceptual depth.
        object1_description = object1.choose_relevant_distinguishing_description_by_conceptual_depth()
        if not object1_description:
            return
        object1_descriptor = object1_description.descriptor

        # Find the corresponding object2_descriptor.
        object2_descriptor = object1_descriptor
        for slippage in self.slippages:
            if slippage.descriptor1 == object1_descriptor:
                object2_descriptor = slippage.descriptor2

        # Find an object with that descriptor in the target string.
        object2_candidates = []
        for object in self.target_string.objects():
            for description in object.relevant_descriptions():
                if description.descriptor == object2_descriptor:
                    object2_candidates.append(object)
        if not object2_candidates:
            return
        values = [obj.inter_string_salience() for obj in object2_candidates]
        index = toolbox.select_list_position(values)
        object2 = object2_candidates[index]

        # If one object spans the whole string and the other does not, fizzle.
        if object1.spans_whole_string() != object2.spans_whole_string():
            return

        # Get the possible concept mappings.
        mappings = self.concept_mappings(object1, object2,
                                         object1.relevant_descriptions(),
                                         object2.relevant_descriptions())
        if not mappings:
            return

        # Decide whether or not to continue based on slippability.
        possible = False
        for mapping in mappings:
            probability = mapping.slippablity() / 100.0
            probability = self.temperature_adjusted_probability(probability)
            if toolbox.flip_coin(probability):
                possible = True
        if not possible:
            return

        # Check if there are any distinguishing mappings.
        distinguished_mappings = [m.distinguishing() for m in mappings]
        if not distinguished_mappings:
            return

        # If both objects span the strings, check if description needs flipped.
        possible_opposite_mappings = []
        for mapping in distinguishing_mappings:
            description_type = mapping.description_type1
            if description_type != 'plato_string_position_category' and \
               description_type != 'plato_bond_facet':
                   possible_opposite_mappings.append(mapping)

        opposite_descriptions = [m.description_type1 for m in mappings]
        if all([object1.string_spanning_group(),
                object2.string_spanning_group(),
                # FIXME: not plato_opposite.is_active(),
                self.all_opposite_concept_mappings(possible_opposite_mappings),
                'plato_direction_category' in opposite_descriptions]):
            old_object2_string_number = object2.string_number
            object2 = object2.flipped_version()
            object2.string_number = old_object2_string_number
            mappings = self.concept_mappings(object1, object2,
                                             object1.relevant_descriptions(),
                                             object2.relevant_descriptions())

        return self.propose_correspondence(object1, object2, mappings, True)

class CorrespondenceStrengthTester(Codelet):
    '''
    Calculate the proposed correspondence's strength and probabilistically
    decides whether or not to post a correspondence builder codelt with
    urgency a function of the strength.
    '''
    def run(self, coderack, slipnet, workspace):
        correspondence = self.arguments[0]
        flip_object2 = self.arguments[1]

        object1 = correspondence.object1
        object2 = correspondence.object2
        flipped = object2.flipped_version()

        # If the objects do not exist anymore, then fizzle.
        objects = workspace.objects()
        if (object1 not in objects) or \
            ((object2 not in objects) and \
            (not (flip_object2 and self.target_string.group_present(flipped)))):
            return

        # Calculate the proposed correspondence's strength.
        correspondence.update_strengths()
        strength = correspondence.total_strength

        # Decide whether to post a corresondpondence builder codelet or not.
        probability = strength / 100.0
        probability = workspace.temperature_adjusted_probability(probability)
        if not toolbox.flip_coin(probability):
            workspace.delete_proposed_correspondence(correspondence)
            return

        # Add some activation to some descriptions.
        for mapping in correspondence.concept_mappings:
            mapping.description_type1.buffer += self.activation
            mapping.descriptor1.buffer += self.activation
            mapping.description_type2.buffer += self.activation
            mapping.descriptor2.buffer += self.activation

        # Set correspondence proposal level.
        correspondence.proposal_level = 2

        # Post the correspondence builder codelet.
        return [Codelet('correspondence_buidler',
                        (correspondence, flip_object2), strength)]