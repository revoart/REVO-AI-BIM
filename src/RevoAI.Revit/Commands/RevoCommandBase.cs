using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevoAI.Revit.Commands;

[Transaction(TransactionMode.Manual)]
[Regeneration(RegenerationOption.Manual)]
public abstract class RevoCommandBase : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        try
        {
            return ExecuteCore(commandData);
        }
        catch (Exception ex)
        {
            RevoLog.Error($"{GetType().Name} failed.", ex);
            message = ex.Message;
            return Result.Failed;
        }
    }

    protected abstract Result ExecuteCore(ExternalCommandData commandData);
}

internal static class PhaseMessages
{
    public static Result Show(string title, string message)
    {
        TaskDialog.Show("Revo AI BIM — " + title, message);
        return Result.Succeeded;
    }
}
