# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from itertools import groupby

from odoo import models, _
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"
    _description = "Product Moves (Stock Move Line)"

    def _action_done(self, cancel_backorder=False):
        super(StockMoveLine, self)._action_done()
        for ml in self.exists():
            ml._check_duplicates()

    def _check_duplicates(self):
        # Unicity of serial tracked product. Search in quants if the sn is
        # already present in stock or delivered to a customer
        if self.tracking == 'serial' and self.lot_id:
            similar_quant = self.env['stock.quant'].search([
                ('lot_id', '=', self.lot_id.id),
                '|',
                ('location_id.usage', 'not in', ('supplier', 'inventory', 'production')),
                ('location_id.scrap_location', '=', True)
            ])
            error_message = _('The serial number %s for product %s is already in another location. Correct your inventory with an inventory adjustment before validating this product move.' % (self.lot_id.name, self.product_id.display_name))

            # Check if SN has been scrapped
            scrapped = any([quant.location_id.scrap_location for quant in similar_quant])
            if scrapped and not self.location_dest_id.scrap_location:
                raise UserError(error_message)
            if similar_quant:
                # the following step will group the quants by location usage
                # if similar_quant =
                #   1 in customer in PACK1
                #   1 in customer in PACK2
                #   -1 in stock in PACK3
                #   -1 in output without pack
                #   1 in stock without pack
                # The group_by becomes
                #  2 in customer
                #  -1 in internal (+1 -1 -1 = -1)

                # First, we sort the quant by location usage
                sq = sorted([(q.location_id.usage, q.quantity) for q in similar_quant], key=lambda x: x[0])
                # -> [('internal', 1), ('customer', 1), ('internal', -1), ('internal', -1), ('customer', 1)]

                # Second, we group by location usage and sum the quantity in the groups
                sq = [(x[0], sum([y[1] for y in x[1]])) for x in groupby(sq, key=lambda x:x[0])]
                # -> [('internal', [('internal',1), ('internal', -1), ('internal', 1)]), ('customer', [('customer', 1), ('customer', 1)])]
                # -> [('internal', -1), ('customer', 2)]

                # Third, we search group with quantity > 1
                duplicates = any([x[1] > 1 for x in sq])
                # -> duplicates = True (for customer usage)

                # Fourth we sum the total quantity
                quantity = sum([x[1] >= 1 for x in sq])
                if duplicates or quantity > 1:
                    raise UserError(error_message)
