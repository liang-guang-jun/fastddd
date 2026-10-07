"""The composition root: the only place that knows every layer exists.

Nothing above this package imports an adapter, and nothing below it imports this
package. That is what makes the layers testable in isolation and the process
assembled in exactly one place, in exactly one order.
"""
